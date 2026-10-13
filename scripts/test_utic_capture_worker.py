from pathlib import Path

import os
import time
from threading import Event, Lock, Thread

import requests
from dotenv import load_dotenv

from ai.contracts import Frame
from ai.detection.capture_worker import CaptureWorker
from ai.detection.frame_sampler import FrameSampler
from ai.detection.health_monitor import CctvHealthMonitor
from ai.detection.quality import check_quality
from ai.detection.sampling_monitor import SamplingPolicyMonitor
from ai.detection.sampling_policy import apply_sampling_mode

from backend.app.cctvs.repository import (
    get_cctv_runtime_state,
    list_monitored_utic_cctvs,
    update_connection_status,
    update_last_frame_at,
    update_video_quality_status,
)

from backend.app.db.session import get_connection

from backend.app.settings.repository import (
    get_monitoring_settings,
)


# =========================================================
# 기본 경로 / 환경설정
# =========================================================

ROOT = Path(__file__).resolve().parents[1]

ENV_PATH = (
    ROOT
    / "backend"
    / ".env"
)


# =========================================================
# UTIC URL
# =========================================================

UTIC_BASE_URL = (
    "https://www.utic.go.kr"
)

UTIC_OPEN_DATA_URL = (
    f"{UTIC_BASE_URL}"
    "/guide/cctvOpenData.do"
)

UTIC_CCTV_INFO_URL = (
    f"{UTIC_BASE_URL}"
    "/map/getCctvInfoById.do"
)


# =========================================================
# 테스트 설정
# =========================================================

# last_frame_at DB 갱신 주기
LAST_FRAME_DB_INTERVAL_SEC = 5.0

# Health Monitor가 CCTV 상태를 확인하는 주기
HEALTH_CHECK_INTERVAL_SEC = 2.0

# 이 시간 동안 last_frame_at 변화가 없으면 stale
STALE_AFTER_SEC = 20.0

# Health Monitor 시작 후 정상 상태 확인 시간
NORMAL_RUN_SEC = 8.0

# 재연결 후 정상 heartbeat 확인 시간
RECOVERY_RUN_SEC = 8.0

# Resolver를 포함한 최초 연결 대기 시간
INITIAL_CONNECT_TIMEOUT_SEC = 45.0

# SamplingPolicyMonitor DB polling 주기
SAMPLING_MONITOR_CHECK_INTERVAL_SEC = 0.5

# OFF 상태에서 실제 sampled frame이 생기지 않는지 확인할 시간
OFF_HOLD_SEC = 4.0

# 실제 샘플 간격 검증 허용 오차
SAMPLE_INTERVAL_EARLY_TOLERANCE_SEC = 0.75
SAMPLE_INTERVAL_LATE_TOLERANCE_SEC = 4.0


# =========================================================
# UTIC 인증키
# =========================================================


def load_utic_key() -> str:
    """
    backend/.env에서 UTIC 인증키를 읽는다.
    """

    load_dotenv(
        dotenv_path=ENV_PATH
    )

    key = os.getenv(
        "UTIC_CCTV_KEY"
    )

    if not key:
        raise RuntimeError(
            "backend/.env에 "
            "UTIC_CCTV_KEY가 없습니다."
        )

    return key


# =========================================================
# DB에서 현재 감시 대상 CCTV 조회
# =========================================================


def get_monitored_utic_cctv() -> dict:
    """
    DB에서 현재 감시 대상인
    UTIC CCTV 한 대를 가져온다.
    """

    with get_connection() as connection:

        cctvs = (
            list_monitored_utic_cctvs(
                connection
            )
        )

    if not cctvs:
        raise RuntimeError(
            "현재 감시 대상인 "
            "UTIC CCTV가 없습니다."
        )

    return cctvs[0]


# =========================================================
# UTIC Stream Resolver
# =========================================================


def get_utic_stream_url(
    external_cctv_id: str,
) -> tuple[str, dict]:
    """
    UTIC external_cctv_id를 이용해
    현재 CCTV 상세정보를 조회하고
    실제 HLS Stream URL을 생성한다.

    이 함수는 최초 연결뿐 아니라
    재연결할 때도 다시 호출할 수 있다.
    """

    key = load_utic_key()

    with requests.Session() as session:

        # -------------------------------------------------
        # 1. UTIC 개방데이터 페이지 접근
        # -------------------------------------------------

        page_response = session.get(
            UTIC_OPEN_DATA_URL,
            params={
                "key": key,
            },
            timeout=20,
        )

        page_response.raise_for_status()

        # -------------------------------------------------
        # 2. CCTV 상세정보 조회
        # -------------------------------------------------

        info_response = session.get(
            UTIC_CCTV_INFO_URL,
            params={
                "cctvId":
                    external_cctv_id,
            },
            headers={
                "Referer":
                    page_response.url,

                "X-Requested-With":
                    "XMLHttpRequest",
            },
            timeout=20,
        )

        info_response.raise_for_status()

        data = info_response.json()

    # -----------------------------------------------------
    # 3. 현재 Stream ID 확인
    # -----------------------------------------------------

    stream_id = data.get(
        "ID"
    )

    if not stream_id:
        raise RuntimeError(
            "UTIC CCTV Stream ID가 없습니다."
        )

    # -----------------------------------------------------
    # 4. 실제 HLS URL 생성
    # -----------------------------------------------------

    stream_url = (
        "https://cctvsec.ktict.co.kr/"
        + stream_id
    )

    return (
        stream_url,
        data,
    )


# =========================================================
# 상태 전이 검증
# =========================================================


def contains_subsequence(
    values: list[str],
    expected: list[str],
) -> bool:
    """
    values 안에 expected 순서가
    중간 값이 있더라도 순서대로 존재하는지 확인한다.
    """

    expected_index = 0

    for value in values:

        if (
            expected_index
            < len(expected)
            and value
            == expected[expected_index]
        ):
            expected_index += 1

    return (
        expected_index
        == len(expected)
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print("=" * 70)

    print(
        "OCTV UTIC + DB + DYNAMIC STREAM "
        "RESOLVER + RUNTIME SAMPLING MODE "
        "INTEGRATION TEST"
    )

    print("=" * 70)

    # =====================================================
    # 1. DB에서 감시 대상 CCTV 조회
    # =====================================================

    print()

    print(
        "[1] DB 감시 대상 CCTV 조회"
    )

    cctv = (
        get_monitored_utic_cctv()
    )

    cctv_id = int(
        cctv["id"]
    )

    original_mode = str(
        cctv["monitored_mode"]
    ).upper()

    print(
        f"OCTV CCTV ID      : "
        f"{cctv_id}"
    )

    print(
        f"External CCTV ID  : "
        f"{cctv['external_cctv_id']}"
    )

    print(
        f"이름              : "
        f"{cctv['name']}"
    )

    print(
        f"Provider          : "
        f"{cctv['provider']}"
    )

    print(
        f"Monitoring Mode   : "
        f"{original_mode}"
    )

    # =====================================================
    # 2. monitoring_settings 조회
    # =====================================================

    print()

    print(
        "[2] Monitoring Settings 조회"
    )

    with get_connection() as connection:

        monitoring_settings = (
            get_monitoring_settings(
                connection
            )
        )

    if monitoring_settings is None:
        raise RuntimeError(
            "monitoring_settings가 비어 있습니다."
        )

    # -----------------------------------------------------
    # DB 설정값 변환
    # -----------------------------------------------------

    base_interval_sec = float(
        monitoring_settings[
            "base_analysis_interval_sec"
        ]
    )

    alert_interval_sec = float(
        monitoring_settings[
            "alert_analysis_interval_sec"
        ]
    )

    verify_interval_sec = float(
        monitoring_settings[
            "verify_analysis_interval_sec"
        ]
    )

    quality_threshold = float(
        monitoring_settings[
            "quality_threshold"
        ]
    )

    reconnect_interval_sec = float(
        monitoring_settings[
            "reconnect_interval_sec"
        ]
    )

    max_reconnect_attempts = int(
        monitoring_settings[
            "max_reconnect_attempts"
        ]
    )

    print()

    print(
        "[MONITORING SETTINGS]"
    )

    print(
        f"BASE interval          : "
        f"{base_interval_sec:.1f}초"
    )

    print(
        f"ALERT interval         : "
        f"{alert_interval_sec:.1f}초"
    )

    print(
        f"VERIFY interval        : "
        f"{verify_interval_sec:.1f}초"
    )

    print(
        f"POST_ALERT interval    : "
        f"{base_interval_sec:.1f}초"
    )

    print(
        f"Quality threshold      : "
        f"{quality_threshold:.2f}"
    )

    print(
        f"Reconnect interval     : "
        f"{reconnect_interval_sec:.1f}초"
    )

    print(
        f"Max reconnect attempts : "
        f"{max_reconnect_attempts}회"
    )

    interval_by_mode = {
        "BASE":
            base_interval_sec,

        "ALERT":
            alert_interval_sec,

        "VERIFY":
            verify_interval_sec,

        "POST_ALERT":
            base_interval_sec,

        "OFF":
            None,
    }

    if original_mode not in interval_by_mode:

        raise RuntimeError(
            f"지원하지 않는 monitored_mode입니다: "
            f"{original_mode}"
        )

    # =====================================================
    # 3. Dynamic UTIC Stream Resolver 준비
    # =====================================================

    print()

    print(
        "[3] Dynamic UTIC Stream Resolver 준비"
    )

    resolver_lock = Lock()

    resolver_call_count = 0

    latest_utic_info: dict | None = None

    def resolve_utic_stream_url() -> str:
        """
        CaptureWorker가 연결을 시도할 때마다 호출된다.

        최초 연결:
        → UTIC API 조회

        재연결:
        → UTIC API 다시 조회

        따라서 오래된 Stream URL을 재사용하지 않는다.
        """

        nonlocal resolver_call_count
        nonlocal latest_utic_info

        with resolver_lock:

            resolver_call_count += 1

            call_number = (
                resolver_call_count
            )

        print()

        print(
            f"[UTIC RESOLVER] "
            f"Stream 정보 조회 "
            f"#{call_number}"
        )

        (
            resolved_url,
            utic_info,
        ) = get_utic_stream_url(
            cctv[
                "external_cctv_id"
            ]
        )

        with resolver_lock:

            latest_utic_info = (
                utic_info
            )

        print(
            f"[UTIC RESOLVER] "
            f"CCTV={utic_info.get('CCTVID')} "
            f"/ NAME="
            f"{utic_info.get('CCTVNAME')} "
            f"/ KIND="
            f"{utic_info.get('KIND')} "
            f"/ MOVIE="
            f"{utic_info.get('MOVIE')}"
        )

        # 실제 URL 전체는 출력하지 않음
        print(
            "[UTIC RESOLVER] "
            "Stream URL 획득 완료"
        )

        return resolved_url

    print(
        "연결 시도마다 UTIC Stream 정보를 "
        "다시 조회하도록 설정합니다."
    )

    # =====================================================
    # 4. Sampling Policy 최초 적용
    # =====================================================

    sampler = FrameSampler(
        default_interval_sec=
            base_interval_sec,
    )

    applied_interval_sec = (
        apply_sampling_mode(
            sampler=sampler,
            cctv_id=cctv_id,
            monitored_mode=(
                original_mode
            ),
            settings=(
                monitoring_settings
            ),
        )
    )

    print()

    print(
        "[SAMPLING POLICY - INITIAL]"
    )

    if applied_interval_sec is None:

        print(
            f"CCTV {cctv_id} "
            f"/ mode="
            f"{original_mode} "
            f"→ 분석 비활성화"
        )

    else:

        print(
            f"CCTV {cctv_id} "
            f"/ mode="
            f"{original_mode} "
            f"→ 분석 주기 "
            f"{applied_interval_sec:.1f}초"
        )

    # =====================================================
    # 5. 테스트 상태 준비
    # =====================================================

    received_count = 0

    sampled_count = 0

    # 실제 Sampling이 발생한 monotonic 시각
    sampled_at_monotonic: list[
        float
    ] = []

    counter_lock = Lock()

    started_at = (
        time.monotonic()
    )

    last_frame_db_update_at = 0.0

    last_quality_status = None

    heartbeat_paused = Event()

    initial_connected_event = Event()

    reconnecting_event = Event()

    reconnected_event = Event()

    health_reconnect_requested_event = (
        Event()
    )

    status_lock = Lock()

    status_history: list[str] = []

    seen_reconnecting = False

    health_reconnect_count = 0

    health_reconnect_lock = Lock()

    # mode별 실제 Sampling 간격 기록
    measured_intervals: dict[
        str,
        float,
    ] = {}

    # =====================================================
    # 6. 영상 품질 상태 DB UPDATE
    # =====================================================

    def update_quality_status_if_changed(
        status: str,
    ) -> None:

        nonlocal last_quality_status

        if last_quality_status == status:
            return

        try:

            with get_connection() as connection:

                result = (
                    update_video_quality_status(
                        connection,
                        cctv_id,
                        status,
                    )
                )

            last_quality_status = status

            print(
                f"[DB QUALITY] "
                f"CCTV {cctv_id} "
                f"→ "
                f"{result['video_quality_status']}"
            )

        except Exception as exc:

            print(
                f"[DB QUALITY ERROR] "
                f"CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

    # =====================================================
    # 7. Capture 상태 Callback
    # =====================================================

    def handle_status(
        status: str,
    ) -> None:

        nonlocal seen_reconnecting

        print(
            f"[DB STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

        with status_lock:

            status_history.append(
                status
            )

            if status == "RECONNECTING":

                seen_reconnecting = True

                reconnecting_event.set()

            elif status == "CONNECTED":

                if seen_reconnecting:

                    reconnected_event.set()

                else:

                    initial_connected_event.set()

        try:

            with get_connection() as connection:

                update_connection_status(
                    connection,
                    cctv_id,
                    status,
                )

        except Exception as exc:

            print(
                f"[DB STATUS ERROR] "
                f"CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

        if status in {
            "RECONNECTING",
            "DISCONNECTED",
        }:

            update_quality_status_if_changed(
                "UNAVAILABLE"
            )

    # =====================================================
    # 8. Frame Callback
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        nonlocal received_count
        nonlocal sampled_count
        nonlocal last_frame_db_update_at

        # -------------------------------------------------
        # 전체 수신 Frame
        # -------------------------------------------------

        with counter_lock:

            received_count += 1

            current_received = (
                received_count
            )

        # -------------------------------------------------
        # DB Heartbeat
        # -------------------------------------------------

        now_monotonic = (
            time.monotonic()
        )

        if not heartbeat_paused.is_set():

            should_update_last_frame = (
                last_frame_db_update_at == 0.0
                or (
                    now_monotonic
                    - last_frame_db_update_at
                )
                >= LAST_FRAME_DB_INTERVAL_SEC
            )

            if should_update_last_frame:

                try:

                    with get_connection() as connection:

                        result = (
                            update_last_frame_at(
                                connection,
                                cctv_id,
                                frame.captured_at,
                            )
                        )

                    last_frame_db_update_at = (
                        now_monotonic
                    )

                    print(
                        f"[DB HEARTBEAT] "
                        f"CCTV {cctv_id} "
                        f"last_frame_at="
                        f"{result['last_frame_at']}"
                    )

                except Exception as exc:

                    print(
                        f"[DB HEARTBEAT ERROR] "
                        f"CCTV {cctv_id} "
                        f"/ error={exc}"
                    )

        # -------------------------------------------------
        # 첫 Frame
        # -------------------------------------------------

        if current_received == 1:

            print()

            print(
                "[FIRST FRAME]"
            )

            print(
                f"shape="
                f"{frame.image.shape}"
            )

            print(
                f"captured_at="
                f"{frame.captured_at}"
            )

        # -------------------------------------------------
        # Sampling
        # -------------------------------------------------

        if not sampler.should_sample(
            frame
        ):
            return

        sampled_at = (
            time.monotonic()
        )

        with counter_lock:

            sampled_count += 1

            current_sampled = (
                sampled_count
            )

            sampled_at_monotonic.append(
                sampled_at
            )

        # -------------------------------------------------
        # Quality
        # -------------------------------------------------

        quality_result = (
            check_quality(
                frame,
                threshold=quality_threshold,
            )
        )

        quality_status = (
            "GOOD"
            if quality_result[
                "is_acceptable"
            ]
            else "LOW"
        )

        update_quality_status_if_changed(
            quality_status
        )

        print(
            f"[QUALITY] "
            f"CCTV {frame.cctv_id} "
            f"/ status={quality_status} "
            f"/ threshold={quality_threshold:.2f} "
            f"/ score="
            f"{quality_result['quality_score']:.3f} "
            f"/ brightness="
            f"{quality_result['mean_brightness']:.1f} "
            f"/ sharpness="
            f"{quality_result['laplacian_variance']:.1f} "
            f"/ reason="
            f"{quality_result['reason']}"
        )

        elapsed = (
            sampled_at
            - started_at
        )

        print(
            f"[SAMPLE #{current_sampled}] "
            f"elapsed={elapsed:.2f}s "
            f"/ received="
            f"{current_received} "
            f"/ shape="
            f"{frame.image.shape}"
        )

    # =====================================================
    # 9. CaptureWorker 생성
    # =====================================================

    worker = CaptureWorker(
        cctv_id=cctv_id,

        stream_url_resolver=(
            resolve_utic_stream_url
        ),

        reconnect_delay_sec=(
            reconnect_interval_sec
        ),

        max_reconnect_attempts=(
            max_reconnect_attempts
        ),

        realtime_pacing=False,
    )

    worker_thread = Thread(
        target=worker.run,
        kwargs={
            "on_frame":
                handle_frame,

            "on_status":
                handle_status,
        },
        name=(
            f"utic-capture-"
            f"{cctv_id}"
        ),
    )

    # =====================================================
    # 10. SamplingPolicyMonitor용 DB Provider
    # =====================================================

    def sampling_state_provider() -> list[dict]:
        """
        실행 중인 CCTV 하나의 현재 runtime 상태를 가져온다.

        중요:
        list_monitored_utic_cctvs()는 OFF를 제외하므로
        OFF 전환을 감지할 수 없다.

        따라서 이미 실행 중인 CCTV는
        get_cctv_runtime_state()로 직접 조회한다.
        """

        with get_connection() as connection:

            state = (
                get_cctv_runtime_state(
                    connection=connection,
                    cctv_id=cctv_id,
                )
            )

        if state is None:

            raise RuntimeError(
                f"CCTV {cctv_id}를 "
                "찾을 수 없습니다."
            )

        return [
            state
        ]

    def sampling_settings_provider() -> dict:
        """
        현재 monitoring_settings 최신값을 가져온다.
        """

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

    # =====================================================
    # 11. 테스트용 monitored_mode DB 변경
    # =====================================================

    def set_db_monitored_mode(
        mode: str,
    ) -> None:

        query = """
        UPDATE cctvs
        SET monitored_mode =
            CAST(%s AS monitored_mode_enum)
        WHERE id = %s;
        """

        with get_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    query,
                    (
                        mode,
                        cctv_id,
                    ),
                )

        print()

        print(
            f"[DB MODE CHANGE] "
            f"CCTV {cctv_id} "
            f"→ {mode}"
        )

    # =====================================================
    # 12. Sampling Policy 적용 대기
    # =====================================================

    def wait_for_sampling_state(
        expected_mode: str,
        expected_interval: float | None,
        timeout_sec: float = 6.0,
    ) -> None:

        deadline = (
            time.monotonic()
            + timeout_sec
        )

        while (
            time.monotonic()
            < deadline
        ):

            state = (
                sampling_state_provider()[0]
            )

            actual_mode = str(
                state[
                    "monitored_mode"
                ]
            ).upper()

            actual_interval = (
                sampler.get_interval(
                    cctv_id
                )
            )

            sampling_enabled = (
                sampler.is_enabled(
                    cctv_id
                )
            )

            if actual_mode == expected_mode:

                # OFF
                if expected_interval is None:

                    if not sampling_enabled:

                        print(
                            f"[PASS] "
                            f"{expected_mode} "
                            f"→ 분석 비활성화"
                        )

                        return

                # BASE / ALERT / VERIFY / POST_ALERT
                else:

                    if (
                        sampling_enabled
                        and actual_interval
                        == expected_interval
                    ):

                        print(
                            f"[PASS] "
                            f"{expected_mode} "
                            f"→ "
                            f"{actual_interval:.1f}초 "
                            f"적용"
                        )

                        return

            time.sleep(
                0.1
            )

        raise AssertionError(
            f"{expected_mode} "
            f"Sampling Policy 적용을 "
            f"{timeout_sec:.1f}초 안에 "
            "확인하지 못했습니다."
        )

    # =====================================================
    # 13. 실제 새 Sampling Frame 기다리기
    # =====================================================

    def wait_for_new_samples(
        start_index: int,
        required_count: int,
        timeout_sec: float,
    ) -> list[float]:

        deadline = (
            time.monotonic()
            + timeout_sec
        )

        target_length = (
            start_index
            + required_count
        )

        while (
            time.monotonic()
            < deadline
        ):

            with counter_lock:

                if (
                    len(sampled_at_monotonic)
                    >= target_length
                ):

                    return (
                        sampled_at_monotonic[
                            start_index:
                            target_length
                        ]
                    )

            time.sleep(
                0.1
            )

        with counter_lock:

            current_length = (
                len(sampled_at_monotonic)
            )

        raise AssertionError(
            "새 Sampling Frame을 기다리는 중 "
            "timeout이 발생했습니다. "
            f"start_index={start_index}, "
            f"required={required_count}, "
            f"current_length={current_length}"
        )

    # =====================================================
    # 14. 실제 Sampling 간격 검증
    # =====================================================

    def verify_actual_sampling_interval(
        mode: str,
        expected_interval: float,
    ) -> None:
        """
        DB mode를 실제로 변경한 뒤
        SamplingPolicyMonitor가 반영할 때까지 기다린다.

        그 이후 새 Sample 2개를 기다려
        실제 Frame Sampling 간격을 측정한다.
        """

        set_db_monitored_mode(
            mode
        )

        wait_for_sampling_state(
            expected_mode=mode,
            expected_interval=(
                expected_interval
            ),
        )

        with counter_lock:

            start_index = (
                len(
                    sampled_at_monotonic
                )
            )

        timeout_sec = (
            expected_interval
            * 3.0
            + 10.0
        )

        sample_times = (
            wait_for_new_samples(
                start_index=start_index,
                required_count=2,
                timeout_sec=timeout_sec,
            )
        )

        actual_interval = (
            sample_times[1]
            - sample_times[0]
        )

        measured_intervals[
            mode
        ] = actual_interval

        min_allowed = max(
            0.0,
            (
                expected_interval
                - SAMPLE_INTERVAL_EARLY_TOLERANCE_SEC
            ),
        )

        max_allowed = (
            expected_interval
            + SAMPLE_INTERVAL_LATE_TOLERANCE_SEC
        )

        print(
            f"[ACTUAL SAMPLE INTERVAL] "
            f"{mode} "
            f"expected="
            f"{expected_interval:.1f}s "
            f"/ actual="
            f"{actual_interval:.2f}s "
            f"/ allowed="
            f"{min_allowed:.2f}"
            f"~"
            f"{max_allowed:.2f}s"
        )

        if not (
            min_allowed
            <= actual_interval
            <= max_allowed
        ):

            raise AssertionError(
                f"{mode} 실제 Sampling 간격이 "
                "허용 범위를 벗어났습니다. "
                f"expected="
                f"{expected_interval:.1f}, "
                f"actual="
                f"{actual_interval:.2f}"
            )

        print(
            f"[PASS] "
            f"{mode} "
            f"실제 Frame Sampling 주기 확인"
        )

    # =====================================================
    # 15. Health Monitor용 DB 상태 조회
    # =====================================================

    def health_state_provider() -> list[dict]:

        with get_connection() as connection:

            rows = (
                list_monitored_utic_cctvs(
                    connection
                )
            )

        return rows

    # =====================================================
    # 16. Health Monitor → 재연결 요청
    # =====================================================

    def health_reconnect_requester(
        requested_cctv_id: int,
    ) -> None:

        nonlocal health_reconnect_count

        if requested_cctv_id != cctv_id:

            raise LookupError(
                f"테스트 Worker가 없는 "
                f"CCTV입니다: "
                f"{requested_cctv_id}"
            )

        with health_reconnect_lock:

            health_reconnect_count += 1

            count = (
                health_reconnect_count
            )

        print()

        print(
            f"[HEALTH ACTION] "
            f"CCTV {requested_cctv_id} "
            f"CaptureWorker 재연결 요청 "
            f"#{count}"
        )

        worker.request_reconnect()

        health_reconnect_requested_event.set()

    # =====================================================
    # 17. Monitor 생성
    # =====================================================

    health_monitor = CctvHealthMonitor(
        check_interval_sec=(
            HEALTH_CHECK_INTERVAL_SEC
        ),
        stale_after_sec=(
            STALE_AFTER_SEC
        ),
    )

    health_monitor_thread = Thread(
        target=health_monitor.run,
        kwargs={
            "state_provider":
                health_state_provider,

            "reconnect_requester":
                health_reconnect_requester,
        },
        name="cctv-health-monitor",
    )

    sampling_monitor = (
        SamplingPolicyMonitor(
            sampler=sampler,
            check_interval_sec=(
                SAMPLING_MONITOR_CHECK_INTERVAL_SEC
            ),
        )
    )

    sampling_monitor_thread = Thread(
        target=sampling_monitor.run,
        kwargs={
            "state_provider":
                sampling_state_provider,

            "settings_provider":
                sampling_settings_provider,
        },
        name=(
            "sampling-policy-monitor-"
            "utic-test"
        ),
    )

    # =====================================================
    # 18. CaptureWorker 시작
    # =====================================================

    print()

    print(
        "[4] CaptureWorker 시작"
    )

    worker_thread.start()

    print(
        "첫 CONNECTED 상태를 기다립니다."
    )

    if not initial_connected_event.wait(
        timeout=INITIAL_CONNECT_TIMEOUT_SEC
    ):

        worker.stop()

        worker_thread.join(
            timeout=5
        )

        raise RuntimeError(
            "CaptureWorker가 "
            "CONNECTED 상태가 되지 않았습니다."
        )

    print(
        "[PASS] 최초 CONNECTED 확인"
    )

    # -----------------------------------------------------
    # 최초 Resolver 호출 확인
    # -----------------------------------------------------

    with resolver_lock:

        initial_resolver_call_count = (
            resolver_call_count
        )

        first_utic_info = (
            latest_utic_info
        )

    print()

    print(
        "[STREAM RESOLVER CHECK]"
    )

    print(
        f"최초 연결까지 Resolver 호출 수 : "
        f"{initial_resolver_call_count}"
    )

    if first_utic_info is not None:

        print(
            f"UTIC CCTV ID : "
            f"{first_utic_info.get('CCTVID')}"
        )

        print(
            f"UTIC 이름    : "
            f"{first_utic_info.get('CCTVNAME')}"
        )

    if initial_resolver_call_count < 1:

        worker.stop()

        worker_thread.join(
            timeout=5
        )

        raise AssertionError(
            "최초 연결 전에 Stream Resolver가 "
            "호출되지 않았습니다."
        )

    # =====================================================
    # 19. SamplingPolicyMonitor 시작
    #     + 실제 DB mode Runtime 전환
    # =====================================================

    print()

    print("=" * 70)

    print(
        "[5] 실제 UTIC Frame "
        "+ Runtime Sampling Mode 테스트"
    )

    print("=" * 70)

    sampling_monitor_thread.start()

    try:

        # 최초 DB 상태를 읽을 시간
        time.sleep(
            1.0
        )

        # -------------------------------------------------
        # BASE
        # -------------------------------------------------

        verify_actual_sampling_interval(
            mode="BASE",
            expected_interval=(
                base_interval_sec
            ),
        )

        # -------------------------------------------------
        # ALERT
        # -------------------------------------------------

        verify_actual_sampling_interval(
            mode="ALERT",
            expected_interval=(
                alert_interval_sec
            ),
        )

        # -------------------------------------------------
        # VERIFY
        # -------------------------------------------------

        verify_actual_sampling_interval(
            mode="VERIFY",
            expected_interval=(
                verify_interval_sec
            ),
        )

        # -------------------------------------------------
        # POST_ALERT
        # -------------------------------------------------

        verify_actual_sampling_interval(
            mode="POST_ALERT",
            expected_interval=(
                base_interval_sec
            ),
        )

        # -------------------------------------------------
        # OFF
        #
        # 실제 Capture는 계속되지만
        # sampled frame은 0개여야 함
        # -------------------------------------------------

        set_db_monitored_mode(
            "OFF"
        )

        wait_for_sampling_state(
            expected_mode="OFF",
            expected_interval=None,
        )

        # OFF 적용 직전 이미
        # should_sample()을 통과한 Frame이
        # 있을 수 있으므로 짧게 안정화
        time.sleep(
            0.5
        )

        with counter_lock:

            off_start_sampled_count = (
                sampled_count
            )

            off_start_received_count = (
                received_count
            )

        print(
            f"[OFF TEST] "
            f"{OFF_HOLD_SEC:.1f}초 동안 "
            "영상 수신은 유지하고 "
            "Sampling만 중단되는지 확인합니다."
        )

        time.sleep(
            OFF_HOLD_SEC
        )

        with counter_lock:

            off_end_sampled_count = (
                sampled_count
            )

            off_end_received_count = (
                received_count
            )

        received_during_off = (
            off_end_received_count
            - off_start_received_count
        )

        sampled_during_off = (
            off_end_sampled_count
            - off_start_sampled_count
        )

        print(
            f"[OFF TEST] "
            f"received 증가="
            f"{received_during_off} "
            f"/ sampled 증가="
            f"{sampled_during_off}"
        )

        if received_during_off <= 0:

            raise AssertionError(
                "OFF 상태에서 실제 CCTV Frame "
                "수신까지 멈췄습니다. "
                "현재 구조에서는 Capture는 유지되고 "
                "Sampling만 중단되어야 합니다."
            )

        if sampled_during_off != 0:

            raise AssertionError(
                "OFF 상태인데 "
                "Sampling Frame이 생성되었습니다. "
                f"count="
                f"{sampled_during_off}"
            )

        print(
            "[PASS] OFF "
            "→ Capture 유지 / Sampling 0개"
        )

        # -------------------------------------------------
        # OFF → BASE
        #
        # set_enabled(False → True) 전환 후
        # 첫 Frame이 다시 Sampling 되어야 함
        # -------------------------------------------------

        with counter_lock:

            before_recovery_sample_count = (
                sampled_count
            )

        set_db_monitored_mode(
            "BASE"
        )

        wait_for_sampling_state(
            expected_mode="BASE",
            expected_interval=(
                base_interval_sec
            ),
        )

        recovery_deadline = (
            time.monotonic()
            + 5.0
        )

        while (
            time.monotonic()
            < recovery_deadline
        ):

            with counter_lock:

                current_sample_count = (
                    sampled_count
                )

            if (
                current_sample_count
                > before_recovery_sample_count
            ):
                break

            time.sleep(
                0.1
            )

        else:

            raise AssertionError(
                "OFF → BASE 이후 "
                "5초 안에 Sampling이 "
                "재개되지 않았습니다."
            )

        print(
            "[PASS] OFF → BASE "
            "실제 Frame Sampling 재개"
        )

    finally:

        # -------------------------------------------------
        # 테스트 실패 여부와 관계없이
        # DB monitored_mode 원상복구
        # -------------------------------------------------

        print()

        print(
            f"[SAMPLING TEST RESTORE] "
            f"원래 mode "
            f"{original_mode}로 복구"
        )

        try:

            set_db_monitored_mode(
                original_mode
            )

            wait_for_sampling_state(
                expected_mode=(
                    original_mode
                ),
                expected_interval=(
                    interval_by_mode[
                        original_mode
                    ]
                ),
            )

        finally:

            sampling_monitor.stop()

            sampling_monitor_thread.join(
                timeout=5
            )

            if (
                sampling_monitor_thread.is_alive()
            ):

                worker.stop()

                worker_thread.join(
                    timeout=5
                )

                raise AssertionError(
                    "SamplingPolicyMonitor Thread가 "
                    "종료되지 않았습니다."
                )

    print(
        "[PASS] Runtime Sampling Mode "
        "테스트 완료 "
        f"/ DB mode 복구="
        f"{original_mode}"
    )

    # =====================================================
    # 20. Health Monitor 시작
    # =====================================================

    print()

    print(
        "[6] Health Monitor 시작"
    )

    health_monitor_thread.start()

    print(
        f"{NORMAL_RUN_SEC:.0f}초 동안 "
        "정상 heartbeat 상태를 확인합니다."
    )

    time.sleep(
        NORMAL_RUN_SEC
    )

    # =====================================================
    # 21. Heartbeat 강제 중단
    # =====================================================

    print()

    print("=" * 70)

    print(
        "[TEST] DB last_frame_at heartbeat "
        "강제 중단"
    )

    print("=" * 70)

    print(
        "※ 실제 CCTV Frame 수신은 "
        "계속 진행됩니다."
    )

    print(
        f"※ {STALE_AFTER_SEC:.0f}초 이상 "
        "last_frame_at이 변하지 않으면 "
        "Health Monitor가 재연결해야 합니다."
    )

    heartbeat_paused.set()

    # =====================================================
    # 22. Health Monitor 재연결 요청 대기
    # =====================================================

    watchdog_timeout = (
        STALE_AFTER_SEC
        + 15.0
    )

    print()

    print(
        "[7] Health Monitor STALE 감지 대기"
    )

    detected = (
        health_reconnect_requested_event.wait(
            timeout=watchdog_timeout
        )
    )

    if not detected:

        heartbeat_paused.clear()

        health_monitor.stop()

        worker.stop()

        health_monitor_thread.join(
            timeout=5
        )

        worker_thread.join(
            timeout=5
        )

        raise AssertionError(
            "last_frame_at이 STALE 상태가 "
            "되었는데 Health Monitor가 "
            "재연결을 요청하지 않았습니다."
        )

    print(
        "[PASS] Health Monitor "
        "재연결 요청 확인"
    )

    # =====================================================
    # 23. RECONNECTING 확인
    # =====================================================

    if not reconnecting_event.wait(
        timeout=5
    ):

        raise AssertionError(
            "Health Monitor의 요청 이후 "
            "CaptureWorker가 RECONNECTING "
            "상태가 되지 않았습니다."
        )

    print(
        "[PASS] RECONNECTING 상태 확인"
    )

    # =====================================================
    # 24. 재연결 후 CONNECTED 확인
    # =====================================================

    reconnect_wait_timeout = (
        reconnect_interval_sec
        + 30.0
    )

    print(
        f"재연결 대기 최대 시간 : "
        f"{reconnect_wait_timeout:.1f}초"
    )

    if not reconnected_event.wait(
        timeout=reconnect_wait_timeout
    ):

        raise AssertionError(
            "CaptureWorker 재연결 이후 "
            "CONNECTED 상태로 "
            "복구되지 않았습니다."
        )

    print(
        "[PASS] 재연결 후 CONNECTED 복구"
    )

    # =====================================================
    # 25. Resolver 재호출 확인
    # =====================================================

    with resolver_lock:

        after_reconnect_resolver_count = (
            resolver_call_count
        )

    print()

    print(
        "[STREAM RESOLVER RECONNECT CHECK]"
    )

    print(
        f"재연결 후 Resolver 호출 수 : "
        f"{after_reconnect_resolver_count}"
    )

    if (
        after_reconnect_resolver_count
        < 2
    ):

        raise AssertionError(
            "재연결 시 UTIC Stream Resolver가 "
            "다시 호출되지 않았습니다."
        )

    print(
        "[PASS] 재연결 시 "
        "UTIC Stream URL 재조회 확인"
    )

    # =====================================================
    # 26. Heartbeat 다시 활성화
    # =====================================================

    print()

    print(
        "[8] DB heartbeat 복구"
    )

    heartbeat_paused.clear()

    print(
        f"{RECOVERY_RUN_SEC:.0f}초 동안 "
        "heartbeat 복구를 확인합니다."
    )

    time.sleep(
        RECOVERY_RUN_SEC
    )

    # =====================================================
    # 27. Health Monitor 먼저 종료
    # =====================================================

    print()

    print(
        "[9] Health Monitor 종료"
    )

    health_monitor.stop()

    health_monitor_thread.join(
        timeout=5
    )

    if (
        health_monitor_thread.is_alive()
    ):

        raise AssertionError(
            "Health Monitor Thread가 "
            "종료되지 않았습니다."
        )

    # =====================================================
    # 28. CaptureWorker 종료
    # =====================================================

    print()

    print(
        "[10] CaptureWorker 종료"
    )

    worker.stop()

    worker_thread.join(
        timeout=10
    )

    if worker_thread.is_alive():

        raise AssertionError(
            "CaptureWorker Thread가 "
            "종료되지 않았습니다."
        )

    # =====================================================
    # 29. 최종 DB 상태 확인
    # =====================================================

    with get_connection() as connection:

        final_cctvs = (
            list_monitored_utic_cctvs(
                connection
            )
        )

    final_cctv = next(
        (
            row
            for row in final_cctvs
            if row["id"] == cctv_id
        ),
        None,
    )

    # =====================================================
    # 30. 최종 결과 정리
    # =====================================================

    with status_lock:

        final_status_history = (
            status_history.copy()
        )

    with health_reconnect_lock:

        final_health_reconnect_count = (
            health_reconnect_count
        )

    with resolver_lock:

        final_resolver_call_count = (
            resolver_call_count
        )

    with counter_lock:

        final_received_count = (
            received_count
        )

        final_sampled_count = (
            sampled_count
        )

    expected_transition = [
        "CONNECTED",
        "RECONNECTING",
        "CONNECTED",
    ]

    transition_ok = (
        contains_subsequence(
            values=final_status_history,
            expected=expected_transition,
        )
    )

    # =====================================================
    # 결과 출력
    # =====================================================

    print()

    print("=" * 70)

    print(
        "RESULT"
    )

    print("=" * 70)

    print(
        f"원래 Monitoring Mode    : "
        f"{original_mode}"
    )

    if applied_interval_sec is None:

        print(
            "최초 적용 분석 주기      : "
            "OFF"
        )

    else:

        print(
            f"최초 적용 분석 주기      : "
            f"{applied_interval_sec:.1f}초"
        )

    print(
        f"Quality threshold      : "
        f"{quality_threshold:.2f}"
    )

    print(
        f"Reconnect interval     : "
        f"{reconnect_interval_sec:.1f}초"
    )

    print(
        f"Max reconnect attempts : "
        f"{max_reconnect_attempts}회"
    )

    print(
        f"Stream Resolver 호출 수 : "
        f"{final_resolver_call_count}"
    )

    print(
        f"전체 수신 Frame         : "
        f"{final_received_count}"
    )

    print(
        f"Sampling Frame         : "
        f"{final_sampled_count}"
    )

    print(
        f"Health 재연결 요청 수   : "
        f"{final_health_reconnect_count}"
    )

    print(
        "상태 History           : "
        + " → ".join(
            final_status_history
        )
    )

    print(
        f"상태 전이 검증          : "
        f"{transition_ok}"
    )

    print()

    print(
        "실제 Runtime Sampling 간격"
    )

    for mode in [
        "BASE",
        "ALERT",
        "VERIFY",
        "POST_ALERT",
    ]:

        actual = (
            measured_intervals.get(
                mode
            )
        )

        expected = (
            interval_by_mode[
                mode
            ]
        )

        if actual is None:

            print(
                f"{mode:<10} : "
                "측정 없음"
            )

        else:

            print(
                f"{mode:<10} : "
                f"expected="
                f"{expected:.1f}s "
                f"/ actual="
                f"{actual:.2f}s"
            )

    print(
        "OFF        : "
        "Capture 유지 / Sampling 0개"
    )

    print(
        "OFF→BASE   : "
        "실제 Frame Sampling 재개"
    )

    if final_cctv is not None:

        print()

        print(
            "최종 DB 상태"
        )

        print(
            f"connection_status    : "
            f"{final_cctv['connection_status']}"
        )

        print(
            f"video_quality_status : "
            f"{final_cctv['video_quality_status']}"
        )

        print(
            f"analysis_status      : "
            f"{final_cctv['analysis_status']}"
        )

        print(
            f"last_frame_at        : "
            f"{final_cctv['last_frame_at']}"
        )

        print(
            f"monitored_mode       : "
            f"{final_cctv['monitored_mode']}"
        )

    # =====================================================
    # 최종 Assert
    # =====================================================

    if (
        final_health_reconnect_count
        != 1
    ):

        raise AssertionError(
            "Health Monitor의 재연결 요청은 "
            "정확히 1번이어야 합니다."
        )

    if not transition_ok:

        raise AssertionError(
            "CONNECTED → RECONNECTING "
            "→ CONNECTED 상태 전이가 "
            "확인되지 않았습니다."
        )

    if final_received_count <= 0:

        raise AssertionError(
            "실제 CCTV Frame이 "
            "수신되지 않았습니다."
        )

    if (
        applied_interval_sec is not None
        and final_sampled_count <= 0
    ):

        raise AssertionError(
            "분석 활성 상태인데 "
            "Sampling Frame이 없습니다."
        )

    if final_resolver_call_count < 2:

        raise AssertionError(
            "최초 연결과 재연결에서 "
            "Stream Resolver가 각각 "
            "호출되지 않았습니다."
        )

    if final_cctv is None:

        raise AssertionError(
            "최종 DB 상태에서 "
            "테스트 CCTV를 찾을 수 없습니다."
        )

    final_mode = str(
        final_cctv[
            "monitored_mode"
        ]
    ).upper()

    if final_mode != original_mode:

        raise AssertionError(
            "테스트 종료 후 "
            "monitored_mode가 "
            "원래 값으로 복구되지 않았습니다. "
            f"original={original_mode}, "
            f"final={final_mode}"
        )

    print()

    print(
        "[SUCCESS] "
        "UTIC Dynamic Stream Resolver "
        "+ DB Settings "
        "+ Runtime Sampling Mode "
        "+ Actual Frame Sampling "
        "+ Quality "
        "+ Health Monitor "
        "+ Auto Reconnect "
        "통합 테스트 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()