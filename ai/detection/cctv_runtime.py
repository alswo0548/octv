from __future__ import annotations

import os
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Mapping

from dotenv import load_dotenv

from ai.contracts import (
    Detection,
    Frame,
)
from ai.detection.capture_manager import (
    CaptureWorkerManager,
)
from ai.detection.capture_worker import (
    CaptureWorker,
)
from ai.detection.detector import (
    YoloDetector,
)
from ai.detection.frame_queue import (
    AnalysisFrameQueue,
)
from ai.detection.frame_sampler import (
    FrameSampler,
)
from ai.detection.health_monitor import (
    CctvHealthMonitor,
)
from ai.detection.reconnect_listener import (
    CctvReconnectListener,
)
from ai.detection.quality import (
    check_quality,
)
from ai.detection.sampling_monitor import (
    SamplingPolicyMonitor,
)
from ai.detection.sampling_policy import (
    apply_sampling_mode,
)
from ai.detection.yolo_worker import (
    YoloPerformance,
    YoloWorker,
)
from ai.detection.utic import (
    get_utic_stream_url,
)

from backend.app.cctvs.repository import (
    list_monitored_runtime_cctvs,
    update_analysis_status,
    update_connection_status,
    update_last_frame_at,
    update_video_quality_status,
)
from backend.app.db.session import (
    get_connection,
)
from backend.app.settings.repository import (
    get_monitoring_settings,
)


# =========================================================
# 기본 경로
# =========================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

BACKEND_ENV_PATH = (
    ROOT
    / "backend"
    / ".env"
)


# =========================================================
# Runtime 기본값
# =========================================================

# DB 감시 대상 CCTV 목록을 다시 확인하는 주기
DEFAULT_MANAGER_SYNC_INTERVAL_SEC = 2.0

# Sampling Mode 변경 확인 주기
DEFAULT_SAMPLING_CHECK_INTERVAL_SEC = 1.0

# CCTV Frame Health 확인 주기
DEFAULT_HEALTH_CHECK_INTERVAL_SEC = 2.0

# 이 시간 동안 last_frame_at이 안 바뀌면 reconnect
DEFAULT_HEALTH_STALE_AFTER_SEC = 20.0

# last_frame_at DB UPDATE 주기
DEFAULT_LAST_FRAME_DB_INTERVAL_SEC = 5.0

# YOLO 분석 대기 Queue 크기
DEFAULT_ANALYSIS_QUEUE_MAXSIZE = 6

# YOLO Queue polling 주기
DEFAULT_YOLO_POLL_INTERVAL_SEC = 0.1


# =========================================================
# CCTV Detection Runtime
# =========================================================


class CctvDetectionRuntime:
    """
    OCTV CCTV 분석 Runtime.

    FastAPI WEB/API 서버와 독립된 별도 프로세스로 실행한다.

    담당 영역:

    DB 감시 CCTV 조회
        ↓
    CaptureWorkerManager
        ↓
    CCTV별 Capture Thread
        ↓
    FrameSampler
        ↓
    Quality Check
        ↓
    AnalysisFrameQueue
        ↓
    YoloWorker

    동시에:

    SamplingPolicyMonitor
        → monitored_mode 변경 반영

    CctvHealthMonitor
        → Frame stale 감지
        → 특정 CCTV reconnect

    현재 YOLO 결과 이후의
    시간 검증 / Incident 생성은
    다음 단계에서 연결한다.
    """

    def __init__(
        self,
        manager_sync_interval_sec: float = (
            DEFAULT_MANAGER_SYNC_INTERVAL_SEC
        ),
        sampling_check_interval_sec: float = (
            DEFAULT_SAMPLING_CHECK_INTERVAL_SEC
        ),
        health_check_interval_sec: float = (
            DEFAULT_HEALTH_CHECK_INTERVAL_SEC
        ),
        health_stale_after_sec: float = (
            DEFAULT_HEALTH_STALE_AFTER_SEC
        ),
        last_frame_db_interval_sec: float = (
            DEFAULT_LAST_FRAME_DB_INTERVAL_SEC
        ),
        analysis_queue_maxsize: int = (
            DEFAULT_ANALYSIS_QUEUE_MAXSIZE
        ),
    ) -> None:

        if manager_sync_interval_sec <= 0:
            raise ValueError(
                "manager_sync_interval_sec은 "
                "0보다 커야 합니다."
            )

        if last_frame_db_interval_sec <= 0:
            raise ValueError(
                "last_frame_db_interval_sec은 "
                "0보다 커야 합니다."
            )

        # -------------------------------------------------
        # 환경변수
        # -------------------------------------------------

        load_dotenv(
            dotenv_path=(
                BACKEND_ENV_PATH
            )
        )

        self._manager_sync_interval_sec = (
            manager_sync_interval_sec
        )

        self._last_frame_db_interval_sec = (
            last_frame_db_interval_sec
        )

        # -------------------------------------------------
        # Runtime 종료 상태
        # -------------------------------------------------

        self._stop_event = Event()

        self._shutdown_lock = Lock()

        self._shutdown_completed = False

        # -------------------------------------------------
        # monitoring_settings 초기 조회
        # -------------------------------------------------

        initial_settings = (
            self._load_monitoring_settings()
        )

        base_interval_sec = float(
            initial_settings[
                "base_analysis_interval_sec"
            ]
        )

        # Quality threshold는
        # Sampling Monitor가 settings를 다시 읽을 때
        # 최신 값으로 갱신된다.
        self._settings_lock = Lock()

        self._quality_threshold = float(
            initial_settings[
                "quality_threshold"
            ]
        )

        # -------------------------------------------------
        # FrameSampler
        # -------------------------------------------------

        self._sampler = FrameSampler(
            default_interval_sec=(
                base_interval_sec
            )
        )

        # -------------------------------------------------
        # YOLO Detector
        # -------------------------------------------------

        model_path = (
            self._resolve_yolo_model_path()
        )

        yolo_device = os.getenv(
            "OCTV_YOLO_DEVICE",
            "cpu",
        )

        yolo_imgsz = int(
            os.getenv(
                "OCTV_YOLO_IMGSZ",
                "640",
            )
        )

        yolo_confidence = float(
            os.getenv(
                "OCTV_YOLO_CONFIDENCE",
                "0.25",
            )
        )

        self._detector = YoloDetector(
            model_path=model_path,
            imgsz=yolo_imgsz,
            device=yolo_device,
            confidence=yolo_confidence,
        )

        self._detector.warmup()

        # -------------------------------------------------
        # YOLO Queue
        # -------------------------------------------------

        self._analysis_frame_queue = (
            AnalysisFrameQueue(
                maxsize=(
                    analysis_queue_maxsize
                )
            )
        )

        # -------------------------------------------------
        # YoloWorker
        # -------------------------------------------------

        self._yolo_worker = YoloWorker(
            frame_queue=(
                self._analysis_frame_queue
            ),
            detect_fn=(
                self._detector.detect
            ),
            poll_interval_sec=(
                DEFAULT_YOLO_POLL_INTERVAL_SEC
            ),
        )

        # -------------------------------------------------
        # CCTV 상태 저장용 Lock
        # -------------------------------------------------

        self._heartbeat_lock = Lock()

        self._last_frame_db_update_at: dict[
            int,
            float,
        ] = {}

        self._quality_lock = Lock()

        self._last_quality_status: dict[
            int,
            str,
        ] = {}

        # -------------------------------------------------
        # CaptureWorkerManager
        # -------------------------------------------------

        self._capture_manager = (
            CaptureWorkerManager(
                worker_factory=(
                    self._create_capture_worker
                ),
                on_frame=(
                    self._handle_frame
                ),
                on_status=(
                    self._handle_capture_status
                ),
            )
        )

        # -------------------------------------------------
        # SamplingPolicyMonitor
        # -------------------------------------------------

        self._sampling_monitor = (
            SamplingPolicyMonitor(
                sampler=(
                    self._sampler
                ),
                check_interval_sec=(
                    sampling_check_interval_sec
                ),
            )
        )

        # -------------------------------------------------
        # CctvHealthMonitor
        # -------------------------------------------------

        self._health_monitor = (
            CctvHealthMonitor(
                check_interval_sec=(
                    health_check_interval_sec
                ),
                stale_after_sec=(
                    health_stale_after_sec
                ),
            )
        )

        # -------------------------------------------------
        # Manual Reconnect Listener
        # -------------------------------------------------

        self._reconnect_listener = (
            CctvReconnectListener(
                stop_event=(
                    self._stop_event
                ),
                reconnect_requester=(
                    self._request_reconnect
                ),
            )
        )

        # -------------------------------------------------
        # Thread 객체
        # -------------------------------------------------

        self._yolo_thread: Thread | None = None

        self._sampling_thread: Thread | None = None

        self._health_thread: Thread | None = None

        self._reconnect_listener_thread: (
            Thread | None
        ) = None

    # =====================================================
    # 환경설정
    # =====================================================

    @staticmethod
    def _resolve_yolo_model_path() -> Path:
        """
        YOLO 모델 경로 결정.

        backend/.env에

        OCTV_YOLO_MODEL_PATH=

        가 있으면 해당 경로 사용.

        없으면 현재 Pipeline 검증용
        프로젝트 루트 yolo11s.pt 사용.

        이후 OCTV 학습 best.pt가 완성되면
        환경변수만 변경하면 된다.
        """

        configured_path = os.getenv(
            "OCTV_YOLO_MODEL_PATH"
        )

        if configured_path:

            path = Path(
                configured_path
            )

            if not path.is_absolute():

                path = (
                    ROOT
                    / path
                )

        else:

            path = (
                ROOT
                / "yolo11s.pt"
            )

        return path.resolve()

    # =====================================================
    # DB Provider
    # =====================================================

    @staticmethod
    def _load_monitored_cctvs() -> list[
        Mapping[str, Any]
    ]:
        demo_enabled = (
            os.getenv(
                "OCTV_DEMO_ENABLED",
                "0",
            ).strip()
            == "1"
        )

        with get_connection() as connection:

            rows = (
                list_monitored_runtime_cctvs(
                    connection,
                    include_demo=(
                        demo_enabled
                    ),
                )
            )

        return rows

    def _load_monitoring_settings(
        self,
    ) -> Mapping[str, Any]:

        with get_connection() as connection:

            settings = (
                get_monitoring_settings(
                    connection
                )
            )

        if settings is None:

            raise RuntimeError(
                "monitoring_settings가 "
                "비어 있습니다."
            )

        return settings

    def _sampling_settings_provider(
        self,
    ) -> Mapping[str, Any]:
        """
        Sampling Monitor가 settings를 읽을 때
        quality_threshold도 같이 최신화한다.
        """

        settings = (
            self._load_monitoring_settings()
        )

        quality_threshold = float(
            settings[
                "quality_threshold"
            ]
        )

        with self._settings_lock:

            self._quality_threshold = (
                quality_threshold
            )

        return settings

    def _get_quality_threshold(
        self,
    ) -> float:

        with self._settings_lock:

            return (
                self._quality_threshold
            )

    # =====================================================
    # CaptureWorker Factory
    # =====================================================

    def _create_capture_worker(
        self,
        cctv: Mapping[str, object],
    ) -> CaptureWorker:

        cctv_id = int(
            cctv[
                "id"
            ]
        )

        external_cctv_id = str(
            cctv[
                "external_cctv_id"
            ]
        )

        provider = str(
            cctv[
                "provider"
            ]
        ).upper()

        configured_stream_url = (
            str(
                cctv[
                    "stream_url"
                ]
            ).strip()
            if cctv.get(
                "stream_url"
            )
            else None
        )

        # Worker가 새로 생성되는 시점의
        # 최신 reconnect 설정 사용
        settings = (
            self._load_monitoring_settings()
        )

        reconnect_interval_sec = float(
            settings[
                "reconnect_interval_sec"
            ]
        )

        max_reconnect_attempts = int(
            settings[
                "max_reconnect_attempts"
            ]
        )

        # =====================================================
        # Demo local MP4
        # =====================================================

        if provider == "DEMO":

            if not configured_stream_url:

                raise RuntimeError(
                    "Demo CCTV에 stream_url이 "
                    "설정되지 않았습니다. "
                    f"cctv_id={cctv_id} "
                    f"external={external_cctv_id}"
                )

            demo_video_dir = Path(
                os.getenv(
                    "OCTV_DEMO_VIDEO_DIR",
                    "demo/videos",
                )
            )

            if not demo_video_dir.is_absolute():

                demo_video_dir = (
                    ROOT
                    / demo_video_dir
                )

            demo_video_dir = (
                demo_video_dir.resolve()
            )

            demo_path = Path(
                configured_stream_url
            )

            if not demo_path.is_absolute():

                demo_path = (
                    demo_video_dir
                    / demo_path
                )

            demo_path = (
                demo_path.resolve()
            )

            try:

                demo_path.relative_to(
                    demo_video_dir
                )

            except ValueError as exc:

                raise RuntimeError(
                    "Demo 영상 경로가 "
                    "OCTV_DEMO_VIDEO_DIR 밖을 "
                    "가리킵니다. "
                    f"path={demo_path}"
                ) from exc

            if not demo_path.exists():

                raise FileNotFoundError(
                    "Demo 영상 파일을 "
                    "찾을 수 없습니다. "
                    f"path={demo_path}"
                )

            print(
                f"[DEMO SOURCE] "
                f"CCTV {cctv_id} "
                f"/ external="
                f"{external_cctv_id} "
                f"/ video={demo_path}"
            )

            return CaptureWorker(
                cctv_id=cctv_id,

                stream_url=str(
                    demo_path
                ),

                reconnect_delay_sec=(
                    reconnect_interval_sec
                ),

                max_reconnect_attempts=(
                    max_reconnect_attempts
                ),

                realtime_pacing=True,
            )

        # =====================================================
        # UTIC
        # =====================================================

        def resolve_stream_url() -> str:

            print(
                f"[UTIC RESOLVER] "
                f"CCTV {cctv_id} "
                f"/ external="
                f"{external_cctv_id}"
            )

            (
                stream_url,
                info,
            ) = get_utic_stream_url(
                external_cctv_id
            )

            print(
                f"[UTIC RESOLVER OK] "
                f"CCTV {cctv_id} "
                f"/ CCTVID="
                f"{info.get('CCTVID')} "
                f"/ NAME="
                f"{info.get('CCTVNAME')}"
            )

            return stream_url

        return CaptureWorker(
            cctv_id=cctv_id,

            stream_url_resolver=(
                resolve_stream_url
            ),

            reconnect_delay_sec=(
                reconnect_interval_sec
            ),

            max_reconnect_attempts=(
                max_reconnect_attempts
            ),

            realtime_pacing=False,
        )

    # =====================================================
    # Capture 상태 Callback
    # =====================================================

    def _handle_capture_status(
        self,
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[RUNTIME CAPTURE] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

        try:

            with get_connection() as connection:

                update_connection_status(
                    connection,
                    cctv_id,
                    status,
                )

        except Exception as exc:

            print(
                f"[RUNTIME DB ERROR] "
                f"connection_status "
                f"/ CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

        # 영상 연결 자체가 없으면
        # Quality 역시 확인 불가능 상태
        if status in {
            "RECONNECTING",
            "DISCONNECTED",
        }:

            self._update_quality_status_if_changed(
                cctv_id=cctv_id,
                status="UNAVAILABLE",
            )

    # =====================================================
    # CCTV Frame Callback
    # =====================================================

    def _handle_frame(
        self,
        frame: Frame,
    ) -> None:

        cctv_id = int(
            frame.cctv_id
        )

        # -------------------------------------------------
        # 1. last_frame_at Heartbeat
        # -------------------------------------------------

        self._update_last_frame_heartbeat(
            frame
        )

        # -------------------------------------------------
        # 2. Sampling
        #
        # OFF라면 여기서 False.
        # Capture Thread 자체는 계속 살아 있다.
        # -------------------------------------------------

        if not self._sampler.should_sample(
            frame
        ):

            return

        # -------------------------------------------------
        # 3. Quality
        # -------------------------------------------------

        threshold = (
            self._get_quality_threshold()
        )

        quality_result = check_quality(
            frame,
            threshold=threshold,
        )

        quality_status = (
            "GOOD"
            if quality_result[
                "is_acceptable"
            ]
            else "LOW"
        )

        self._update_quality_status_if_changed(
            cctv_id=cctv_id,
            status=quality_status,
        )

        if quality_status != "GOOD":

            print(
                f"[RUNTIME QUALITY SKIP] "
                f"CCTV {cctv_id} "
                f"/ score="
                f"{quality_result['quality_score']:.3f} "
                f"/ reason="
                f"{quality_result['reason']}"
            )

            return

        # -------------------------------------------------
        # 4. YOLO Queue
        # -------------------------------------------------

        dropped_frame = (
            self._analysis_frame_queue.put_latest(
                frame
            )
        )

        if dropped_frame is not None:

            print(
                f"[RUNTIME QUEUE DROP] "
                f"old_cctv="
                f"{dropped_frame.cctv_id} "
                f"/ new_cctv="
                f"{cctv_id}"
            )

    # =====================================================
    # DB Heartbeat
    # =====================================================

    def _update_last_frame_heartbeat(
        self,
        frame: Frame,
    ) -> None:

        import time

        cctv_id = int(
            frame.cctv_id
        )

        now_monotonic = (
            time.monotonic()
        )

        should_update = False

        with self._heartbeat_lock:

            previous = (
                self
                ._last_frame_db_update_at
                .get(
                    cctv_id,
                    0.0,
                )
            )

            if (
                previous == 0.0
                or (
                    now_monotonic
                    - previous
                )
                >= self
                ._last_frame_db_interval_sec
            ):

                self._last_frame_db_update_at[
                    cctv_id
                ] = now_monotonic

                should_update = True

        if not should_update:

            return

        try:

            with get_connection() as connection:

                update_last_frame_at(
                    connection,
                    cctv_id,
                    frame.captured_at,
                )

        except Exception as exc:

            print(
                f"[RUNTIME DB ERROR] "
                f"last_frame_at "
                f"/ CCTV {cctv_id} "
                f"/ error={exc}"
            )

    # =====================================================
    # Quality DB 상태
    # =====================================================

    def _update_quality_status_if_changed(
        self,
        cctv_id: int,
        status: str,
    ) -> None:

        with self._quality_lock:

            previous = (
                self
                ._last_quality_status
                .get(
                    cctv_id
                )
            )

        if previous == status:

            return

        try:

            with get_connection() as connection:

                update_video_quality_status(
                    connection,
                    cctv_id,
                    status,
                )

        except Exception as exc:

            print(
                f"[RUNTIME DB ERROR] "
                f"video_quality_status "
                f"/ CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

            # 실패하면 cache를 갱신하지 않는다.
            # 다음 Frame에서 DB UPDATE를 재시도한다.
            return

        with self._quality_lock:

            self._last_quality_status[
                cctv_id
            ] = status

        print(
            f"[RUNTIME QUALITY] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

    # =====================================================
    # YOLO 분석 상태 Callback
    # =====================================================

    @staticmethod
    def _handle_yolo_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[RUNTIME YOLO STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

        try:

            with get_connection() as connection:

                update_analysis_status(
                    connection,
                    cctv_id,
                    status,
                )

        except Exception as exc:

            print(
                f"[RUNTIME DB ERROR] "
                f"analysis_status "
                f"/ CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

    # =====================================================
    # YOLO Result Callback
    # =====================================================

    @staticmethod
    def _handle_yolo_result(
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: YoloPerformance,
    ) -> None:
        """
        현재는 YOLO 결과를 로그로 확인한다.

        다음 단계에서 이 지점에:

        Detection
            ↓
        후보 필터
            ↓
        시간 검증
            ↓
        Incident 생성 / 갱신

        을 연결한다.
        """

        if not detections:

            return

        print(
            f"[RUNTIME DETECTION] "
            f"CCTV {frame.cctv_id} "
            f"/ count={len(detections)} "
            f"/ inference="
            f"{performance.inference_sec:.3f}s"
        )

        for detection in detections:

            print(
                "  - "
                f"type={detection.hazard_type} "
                f"/ confidence="
                f"{detection.confidence:.3f} "
                f"/ bbox="
                f"{detection.bbox}"
            )

    # =====================================================
    # Health Monitor
    # =====================================================

    def _request_reconnect(
        self,
        cctv_id: int,
    ) -> None:

        requested = (
            self
            ._capture_manager
            .request_reconnect(
                cctv_id
            )
        )

        if not requested:

            # HealthMonitor가 이 요청을
            # 성공한 것으로 기록하지 않도록
            # 예외를 발생시킨다.
            raise RuntimeError(
                f"CCTV {cctv_id}의 "
                "실행 중 CaptureWorker가 "
                "없습니다."
            )

    # =====================================================
    # 최초 Sampling Policy 적용
    # =====================================================

    def _apply_initial_sampling_policies(
        self,
        cctvs: list[
            Mapping[str, Any]
        ],
        settings: Mapping[str, Any],
    ) -> None:
        """
        Runtime 시작 직후 Sampling Monitor가
        첫 polling을 하기 전에 Frame이 들어올 수 있다.

        특히 OFF CCTV가 첫 Frame을 YOLO로 보내는
        race condition을 막기 위해
        CaptureWorker 시작 전에 한 번 적용한다.
        """

        for cctv in cctvs:

            cctv_id = int(
                cctv[
                    "id"
                ]
            )

            monitored_mode = str(
                cctv[
                    "monitored_mode"
                ]
            ).upper()

            applied_interval = (
                apply_sampling_mode(
                    sampler=(
                        self._sampler
                    ),
                    cctv_id=cctv_id,
                    monitored_mode=(
                        monitored_mode
                    ),
                    settings=settings,
                )
            )

            if applied_interval is None:

                print(
                    f"[RUNTIME SAMPLING] "
                    f"CCTV {cctv_id} "
                    f"/ mode={monitored_mode} "
                    "→ OFF"
                )

            else:

                print(
                    f"[RUNTIME SAMPLING] "
                    f"CCTV {cctv_id} "
                    f"/ mode={monitored_mode} "
                    f"→ "
                    f"{applied_interval:.1f}s"
                )

    # =====================================================
    # Thread 생성
    # =====================================================

    def _start_yolo_thread(
        self,
    ) -> None:

        self._yolo_thread = Thread(
            target=(
                self._yolo_worker.run
            ),
            kwargs={
                "on_result":
                    self._handle_yolo_result,

                "on_status":
                    self._handle_yolo_status,
            },
            name=(
                "octv-yolo-worker"
            ),
        )

        self._yolo_thread.start()

    def _start_sampling_thread(
        self,
    ) -> None:

        self._sampling_thread = Thread(
            target=(
                self._sampling_monitor.run
            ),
            kwargs={
                "state_provider":
                    self._load_monitored_cctvs,

                "settings_provider":
                    self._sampling_settings_provider,
            },
            name=(
                "octv-sampling-monitor"
            ),
        )

        self._sampling_thread.start()

    def _start_health_thread(
        self,
    ) -> None:

        self._health_thread = Thread(
            target=(
                self._health_monitor.run
            ),
            kwargs={
                "state_provider":
                    self._load_monitored_cctvs,

                "reconnect_requester":
                    self._request_reconnect,
            },
            name=(
                "octv-health-monitor"
            ),
        )

        self._health_thread.start()

    def _start_reconnect_listener_thread(
        self,
    ) -> None:

        self._reconnect_listener_thread = (
            Thread(
                target=(
                    self._reconnect_listener.run
                ),
                name=(
                    "octv-reconnect-listener"
                ),
            )
        )

        self._reconnect_listener_thread.start()

    # =====================================================
    # Capture Worker Sync
    # =====================================================

    def _sync_capture_workers(
        self,
        cctvs: list[
            Mapping[str, Any]
        ]
        | None = None,
    ) -> None:

        if cctvs is None:

            cctvs = (
                self._load_monitored_cctvs()
            )

        result = (
            self
            ._capture_manager
            .sync(
                cctvs
            )
        )

        if (
            result[
                "started"
            ]
            or result[
                "stopped"
            ]
        ):

            print(
                "[RUNTIME SYNC] "
                f"started="
                f"{result['started']} "
                f"/ stopped="
                f"{result['stopped']} "
                f"/ running="
                f"{result['running']}"
            )

    # =====================================================
    # 외부 종료 요청
    # =====================================================

    def request_stop(
        self,
    ) -> None:

        print(
            "[RUNTIME] "
            "종료 요청 수신"
        )

        self._stop_event.set()

    # =====================================================
    # Main
    # =====================================================

    def run_forever(
        self,
    ) -> None:

        print()
        print("=" * 80)
        print(
            "OCTV CCTV DETECTION RUNTIME START"
        )
        print("=" * 80)

        try:

            # ---------------------------------------------
            # 1. 최초 CCTV / Settings
            # ---------------------------------------------

            initial_cctvs = (
                self._load_monitored_cctvs()
            )

            initial_settings = (
                self._sampling_settings_provider()
            )

            print(
                f"[RUNTIME] "
                f"감시 대상 CCTV "
                f"{len(initial_cctvs)}대"
            )

            # ---------------------------------------------
            # 2. Capture 시작 전에
            #    Sampling Policy 선적용
            # ---------------------------------------------

            self._apply_initial_sampling_policies(
                cctvs=(
                    initial_cctvs
                ),
                settings=(
                    initial_settings
                ),
            )

            # ---------------------------------------------
            # 3. YOLO Worker
            # ---------------------------------------------

            self._start_yolo_thread()

            # ---------------------------------------------
            # 4. Sampling Monitor
            # ---------------------------------------------

            self._start_sampling_thread()

            # ---------------------------------------------
            # 5. Capture Worker 시작
            # ---------------------------------------------

            self._sync_capture_workers(
                initial_cctvs
            )

            # ---------------------------------------------
            # 6. Manual Reconnect Listener
            # ---------------------------------------------

            self._start_reconnect_listener_thread()

            # ---------------------------------------------
            # 7. Health Monitor
            # ---------------------------------------------

            self._start_health_thread()

            # ---------------------------------------------
            # 8. Runtime Main Loop
            #
            # is_monitored 대상이 추가/삭제되면
            # Manager가 Worker를 시작/종료한다.
            # ---------------------------------------------

            print(
                "[RUNTIME] "
                "CCTV Runtime 실행 중"
            )

            while not self._stop_event.wait(
                self._manager_sync_interval_sec
            ):

                try:

                    self._sync_capture_workers()

                except Exception as exc:

                    # 일시적인 DB 장애로
                    # 전체 Runtime을 죽이지 않는다.
                    print(
                        "[RUNTIME SYNC ERROR] "
                        f"{exc}"
                    )

        finally:

            self.stop()

    # =====================================================
    # Runtime 전체 종료
    # =====================================================

    def stop(
        self,
    ) -> None:

        with self._shutdown_lock:

            if self._shutdown_completed:

                return

            self._shutdown_completed = True

        print()
        print(
            "[RUNTIME] "
            "전체 종료 시작"
        )

        self._stop_event.set()

        # ---------------------------------------------
        # 1. Monitor 종료 요청
        # ---------------------------------------------

        self._sampling_monitor.stop()

        self._health_monitor.stop()

        # ---------------------------------------------
        # 2. Capture 중지
        #
        # 더 이상 Queue에 새로운 Frame이
        # 들어오지 않도록 Capture부터 종료한다.
        # ---------------------------------------------

        try:

            self._capture_manager.stop_all()

        except Exception as exc:

            print(
                "[RUNTIME STOP ERROR] "
                f"Capture 종료 실패 "
                f"/ {exc}"
            )

        # ---------------------------------------------
        # 3. YOLO 종료
        # ---------------------------------------------

        self._yolo_worker.stop()

        # ---------------------------------------------
        # 4. Monitor Thread join
        # ---------------------------------------------

        self._join_thread(
            self._sampling_thread,
            "Sampling Monitor",
        )

        self._join_thread(
            self._health_thread,
            "Health Monitor",
        )

        self._join_thread(
            self._reconnect_listener_thread,
            "Reconnect Listener",
        )

        self._join_thread(
            self._yolo_thread,
            "YoloWorker",
        )

        print()
        print("=" * 80)
        print(
            "OCTV CCTV DETECTION RUNTIME STOPPED"
        )
        print("=" * 80)

    # =====================================================
    # Thread Join Helper
    # =====================================================

    @staticmethod
    def _join_thread(
        thread: Thread | None,
        name: str,
        timeout_sec: float = 10.0,
    ) -> None:

        if thread is None:

            return

        if not thread.is_alive():

            return

        thread.join(
            timeout=(
                timeout_sec
            )
        )

        if thread.is_alive():

            print(
                f"[RUNTIME STOP WARNING] "
                f"{name} Thread가 "
                f"{timeout_sec:.1f}초 내에 "
                "종료되지 않았습니다."
            )