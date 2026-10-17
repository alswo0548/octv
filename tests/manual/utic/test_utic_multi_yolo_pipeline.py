from __future__ import annotations

import time
from pathlib import Path
from threading import Lock, Thread

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
from ai.detection.quality import (
    check_quality,
)
from ai.detection.sampling_policy import (
    apply_sampling_mode,
)
from ai.detection.yolo_worker import (
    YoloPerformance,
    YoloWorker,
)

from backend.app.cctvs.repository import (
    list_monitored_utic_cctvs,
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

# 기존 단일 UTIC 테스트에서
# 이미 검증된 Stream URL 조회 로직 재사용
from ai.detection.utic import (
    get_utic_stream_url,
)


# =========================================================
# 경로
# =========================================================

ROOT = Path(
    __file__
).resolve().parents[3]

YOLO_MODEL_PATH = (
    ROOT
    / "yolo11s.pt"
)


# =========================================================
# 테스트 설정
# =========================================================

TEST_CCTV_COUNT = 3

MIN_REQUIRED_CCTV_COUNT = 2

INITIAL_CONNECT_TIMEOUT_SEC = 60.0

FIRST_FRAME_TIMEOUT_SEC = 30.0

# BASE가 현재 5초이므로
# 각 CCTV에서 여러 번 Sampling / YOLO가 일어나도록
# 충분히 기다린다.
PIPELINE_RUN_SEC = 18.0

LAST_FRAME_DB_INTERVAL_SEC = 5.0

YOLO_QUEUE_MAXSIZE = 4


# =========================================================
# 대기 Helper
# =========================================================


def wait_until(
    condition,
    timeout_sec: float,
    description: str,
) -> None:

    deadline = (
        time.monotonic()
        + timeout_sec
    )

    while (
        time.monotonic()
        < deadline
    ):

        if condition():
            return

        time.sleep(
            0.1
        )

    raise TimeoutError(
        f"{description} "
        f"대기시간을 초과했습니다. "
        f"timeout={timeout_sec:.1f}s"
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print("=" * 80)

    print(
        "OCTV REAL UTIC MULTI-CCTV "
        "SAMPLING + QUALITY + YOLO PIPELINE TEST"
    )

    print("=" * 80)

    # =====================================================
    # 1. 감시 대상 CCTV 조회
    # =====================================================

    with get_connection() as connection:

        monitored_cctvs = (
            list_monitored_utic_cctvs(
                connection
            )
        )

    if (
        len(monitored_cctvs)
        < MIN_REQUIRED_CCTV_COUNT
    ):

        raise RuntimeError(
            "실제 Multi-CCTV 테스트에는 "
            f"최소 {MIN_REQUIRED_CCTV_COUNT}대의 "
            "감시 대상 UTIC CCTV가 필요합니다."
        )

    test_cctvs = (
        monitored_cctvs[
            :min(
                TEST_CCTV_COUNT,
                len(monitored_cctvs),
            )
        ]
    )

    test_ids = [
        int(
            cctv["id"]
        )
        for cctv in test_cctvs
    ]

    print()
    print(
        f"[1] 테스트 CCTV "
        f"{len(test_cctvs)}대"
    )

    for cctv in test_cctvs:

        print(
            f"  - id={cctv['id']} "
            f"/ external="
            f"{cctv['external_cctv_id']} "
            f"/ name={cctv['name']} "
            f"/ mode="
            f"{cctv['monitored_mode']}"
        )

    # =====================================================
    # 2. monitoring_settings 조회
    # =====================================================

    with get_connection() as connection:

        settings = (
            get_monitoring_settings(
                connection
            )
        )

    if settings is None:

        raise RuntimeError(
            "monitoring_settings가 없습니다."
        )

    base_interval_sec = float(
        settings[
            "base_analysis_interval_sec"
        ]
    )

    quality_threshold = float(
        settings[
            "quality_threshold"
        ]
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

    print()
    print("[2] Monitoring Settings")

    print(
        f"BASE interval        : "
        f"{base_interval_sec:.1f}s"
    )

    print(
        f"Quality threshold    : "
        f"{quality_threshold:.2f}"
    )

    print(
        f"Reconnect interval   : "
        f"{reconnect_interval_sec:.1f}s"
    )

    print(
        f"Reconnect max        : "
        f"{max_reconnect_attempts}"
    )

    # =====================================================
    # 3. FrameSampler
    # =====================================================

    sampler = FrameSampler(
        default_interval_sec=(
            base_interval_sec
        )
    )

    print()
    print(
        "[3] CCTV별 Sampling Policy 적용"
    )

    for cctv in test_cctvs:

        cctv_id = int(
            cctv["id"]
        )

        mode = str(
            cctv[
                "monitored_mode"
            ]
        ).upper()

        applied_interval = (
            apply_sampling_mode(
                sampler=sampler,
                cctv_id=cctv_id,
                monitored_mode=mode,
                settings=settings,
            )
        )

        if applied_interval is None:

            print(
                f"CCTV {cctv_id} "
                f"/ mode={mode} "
                "→ Sampling OFF"
            )

        else:

            print(
                f"CCTV {cctv_id} "
                f"/ mode={mode} "
                f"→ {applied_interval:.1f}s"
            )

    # =====================================================
    # 4. YOLO Pipeline
    # =====================================================

    print()
    print(
        "[4] YOLO Pipeline 준비"
    )

    if not YOLO_MODEL_PATH.exists():

        raise FileNotFoundError(
            "YOLO 모델을 찾을 수 없습니다: "
            f"{YOLO_MODEL_PATH}"
        )

    detector = YoloDetector(
        model_path=(
            YOLO_MODEL_PATH
        ),
        imgsz=640,
        device="cpu",
        confidence=0.25,
    )

    detector.warmup()

    analysis_frame_queue = (
        AnalysisFrameQueue(
            maxsize=(
                YOLO_QUEUE_MAXSIZE
            )
        )
    )

    yolo_worker = (
        YoloWorker(
            frame_queue=(
                analysis_frame_queue
            ),
            detect_fn=(
                detector.detect
            ),
            poll_interval_sec=0.1,
        )
    )

    print(
        "[PASS] "
        "YoloDetector + Queue + "
        "YoloWorker 준비 완료"
    )

    # =====================================================
    # 5. 테스트 통계
    # =====================================================

    stats_lock = Lock()

    stats: dict[
        int,
        dict[str, int],
    ] = {}

    for cctv_id in test_ids:

        stats[
            cctv_id
        ] = {
            "received": 0,
            "sampled": 0,
            "quality_good": 0,
            "quality_low": 0,
            "enqueued": 0,
            "queue_dropped": 0,
            "yolo_results": 0,
            "detections": 0,
        }

    status_lock = Lock()

    status_history: dict[
        int,
        list[str],
    ] = {
        cctv_id: []
        for cctv_id in test_ids
    }

    heartbeat_lock = Lock()

    last_frame_db_update_at: dict[
        int,
        float,
    ] = {}

    quality_lock = Lock()

    last_quality_status: dict[
        int,
        str,
    ] = {}

    # =====================================================
    # 6. Quality DB Update
    # =====================================================

    def update_quality_if_changed(
        cctv_id: int,
        status: str,
    ) -> None:

        with quality_lock:

            previous = (
                last_quality_status.get(
                    cctv_id
                )
            )

            if previous == status:

                return

            last_quality_status[
                cctv_id
            ] = status

        try:

            with get_connection() as connection:

                update_video_quality_status(
                    connection,
                    cctv_id,
                    status,
                )

        except Exception as exc:

            print(
                f"[DB QUALITY ERROR] "
                f"CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

    # =====================================================
    # 7. Capture Status Callback
    # =====================================================

    def handle_capture_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[CAPTURE STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

        with status_lock:

            status_history.setdefault(
                cctv_id,
                [],
            ).append(
                status
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
                f"[DB STATUS ERROR] "
                f"CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

        if status in {
            "RECONNECTING",
            "DISCONNECTED",
        }:

            update_quality_if_changed(
                cctv_id,
                "UNAVAILABLE",
            )

    # =====================================================
    # 8. Capture Frame Callback
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        cctv_id = int(
            frame.cctv_id
        )

        # ---------------------------------------------
        # 전체 수신 Frame
        # ---------------------------------------------

        with stats_lock:

            stats[
                cctv_id
            ][
                "received"
            ] += 1

            received_count = (
                stats[
                    cctv_id
                ][
                    "received"
                ]
            )

        # ---------------------------------------------
        # DB Heartbeat
        # ---------------------------------------------

        now_monotonic = (
            time.monotonic()
        )

        should_update_heartbeat = (
            False
        )

        with heartbeat_lock:

            previous = (
                last_frame_db_update_at.get(
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
                >= LAST_FRAME_DB_INTERVAL_SEC
            ):

                last_frame_db_update_at[
                    cctv_id
                ] = now_monotonic

                should_update_heartbeat = (
                    True
                )

        if should_update_heartbeat:

            try:

                with get_connection() as connection:

                    update_last_frame_at(
                        connection,
                        cctv_id,
                        frame.captured_at,
                    )

            except Exception as exc:

                print(
                    f"[DB HEARTBEAT ERROR] "
                    f"CCTV {cctv_id} "
                    f"/ error={exc}"
                )

        # 첫 Frame만 로그
        if received_count == 1:

            print(
                f"[FIRST FRAME] "
                f"CCTV {cctv_id} "
                f"/ shape="
                f"{frame.image.shape}"
            )

        # ---------------------------------------------
        # Sampling
        # ---------------------------------------------

        if not sampler.should_sample(
            frame
        ):

            return

        with stats_lock:

            stats[
                cctv_id
            ][
                "sampled"
            ] += 1

            sampled_count = (
                stats[
                    cctv_id
                ][
                    "sampled"
                ]
            )

        # ---------------------------------------------
        # Quality Check
        # ---------------------------------------------

        quality_result = (
            check_quality(
                frame,
                threshold=(
                    quality_threshold
                ),
            )
        )

        quality_status = (
            "GOOD"
            if quality_result[
                "is_acceptable"
            ]
            else "LOW"
        )

        update_quality_if_changed(
            cctv_id,
            quality_status,
        )

        with stats_lock:

            if quality_status == "GOOD":

                stats[
                    cctv_id
                ][
                    "quality_good"
                ] += 1

            else:

                stats[
                    cctv_id
                ][
                    "quality_low"
                ] += 1

        print(
            f"[SAMPLE #{sampled_count}] "
            f"CCTV {cctv_id} "
            f"/ quality="
            f"{quality_status} "
            f"/ score="
            f"{quality_result['quality_score']:.3f} "
            f"/ reason="
            f"{quality_result['reason']}"
        )

        # ---------------------------------------------
        # GOOD Frame만 YOLO Queue
        # ---------------------------------------------

        if quality_status != "GOOD":

            return

        dropped_frame = (
            analysis_frame_queue.put_latest(
                frame
            )
        )

        with stats_lock:

            stats[
                cctv_id
            ][
                "enqueued"
            ] += 1

            if dropped_frame is not None:

                dropped_cctv_id = int(
                    dropped_frame.cctv_id
                )

                if (
                    dropped_cctv_id
                    in stats
                ):

                    stats[
                        dropped_cctv_id
                    ][
                        "queue_dropped"
                    ] += 1

        if dropped_frame is not None:

            print(
                "[QUEUE DROP] "
                f"CCTV "
                f"{dropped_frame.cctv_id} "
                "오래된 Frame 제거"
            )

    # =====================================================
    # 9. YOLO Status Callback
    # =====================================================

    def handle_yolo_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[YOLO STATUS] "
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
                f"[DB ANALYSIS ERROR] "
                f"CCTV {cctv_id} "
                f"/ status={status} "
                f"/ error={exc}"
            )

    # =====================================================
    # 10. YOLO Result Callback
    # =====================================================

    def handle_yolo_result(
        frame: Frame,
        detections: list[
            Detection
        ],
        performance: YoloPerformance,
    ) -> None:

        cctv_id = int(
            frame.cctv_id
        )

        with stats_lock:

            stats[
                cctv_id
            ][
                "yolo_results"
            ] += 1

            stats[
                cctv_id
            ][
                "detections"
            ] += len(
                detections
            )

            result_count = (
                stats[
                    cctv_id
                ][
                    "yolo_results"
                ]
            )

        print(
            f"[YOLO RESULT #{result_count}] "
            f"CCTV {cctv_id} "
            f"/ detections="
            f"{len(detections)} "
            f"/ queue_wait="
            f"{performance.queue_wait_sec:.3f}s "
            f"/ inference="
            f"{performance.inference_sec:.3f}s "
            f"/ total="
            f"{performance.total_latency_sec:.3f}s"
        )

    # =====================================================
    # 11. Worker Factory
    # =====================================================

    def worker_factory(
        cctv,
    ) -> CaptureWorker:

        cctv_id = int(
            cctv["id"]
        )

        external_cctv_id = str(
            cctv[
                "external_cctv_id"
            ]
        )

        def resolve_stream_url() -> str:

            print(
                f"[UTIC RESOLVER] "
                f"CCTV {cctv_id} "
                f"/ external="
                f"{external_cctv_id}"
            )

            stream_url, info = (
                get_utic_stream_url(
                    external_cctv_id
                )
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
    # 12. Manager / YOLO Thread 준비
    # =====================================================

    manager = CaptureWorkerManager(
        worker_factory=(
            worker_factory
        ),
        on_frame=(
            handle_frame
        ),
        on_status=(
            handle_capture_status
        ),
    )

    yolo_thread = Thread(
        target=(
            yolo_worker.run
        ),
        kwargs={
            "on_result":
                handle_yolo_result,

            "on_status":
                handle_yolo_status,
        },
        name=(
            "multi-cctv-yolo-worker"
        ),
    )

    try:

        # =================================================
        # 13. YOLO Worker 시작
        # =================================================

        print()
        print(
            "[5] YoloWorker 시작"
        )

        yolo_thread.start()

        # =================================================
        # 14. CaptureWorkerManager 시작
        # =================================================

        print()
        print(
            "[6] 실제 UTIC CCTV "
            "Capture Thread 시작"
        )

        result = (
            manager.sync(
                test_cctvs
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        # =================================================
        # 15. 전체 CONNECTED 확인
        # =================================================

        def all_connected() -> bool:

            with status_lock:

                return all(
                    "CONNECTED"
                    in status_history.get(
                        cctv_id,
                        [],
                    )
                    for cctv_id
                    in test_ids
                )

        wait_until(
            condition=(
                all_connected
            ),
            timeout_sec=(
                INITIAL_CONNECT_TIMEOUT_SEC
            ),
            description=(
                "모든 CCTV CONNECTED"
            ),
        )

        print(
            "[PASS] "
            "모든 CCTV CONNECTED"
        )

        # =================================================
        # 16. 전체 첫 Frame 확인
        # =================================================

        def all_received() -> bool:

            with stats_lock:

                return all(
                    stats[
                        cctv_id
                    ][
                        "received"
                    ]
                    > 0
                    for cctv_id
                    in test_ids
                )

        wait_until(
            condition=(
                all_received
            ),
            timeout_sec=(
                FIRST_FRAME_TIMEOUT_SEC
            ),
            description=(
                "모든 CCTV 첫 Frame"
            ),
        )

        print(
            "[PASS] "
            "모든 CCTV 첫 Frame 수신"
        )

        # =================================================
        # 17. 실제 Multi-CCTV Pipeline 실행
        # =================================================

        print()
        print(
            f"[7] {PIPELINE_RUN_SEC:.1f}초 동안 "
            "Sampling → Quality → "
            "Queue → YOLO 실행"
        )

        time.sleep(
            PIPELINE_RUN_SEC
        )

    finally:

        # =================================================
        # 18. Capture 종료
        # =================================================

        print()
        print(
            "[CLEANUP] "
            "Capture Thread 전체 종료"
        )

        manager.stop_all()

        # =================================================
        # 19. YOLO 종료
        # =================================================

        print(
            "[CLEANUP] "
            "YoloWorker 종료"
        )

        yolo_worker.stop()

        yolo_thread.join(
            timeout=10
        )

        if yolo_thread.is_alive():

            raise RuntimeError(
                "YoloWorker Thread가 "
                "종료되지 않았습니다."
            )

    # =====================================================
    # 20. 최종 결과
    # =====================================================

    print()
    print("=" * 80)
    print("[FINAL STATS]")
    print("=" * 80)

    with stats_lock:

        final_stats = {
            cctv_id:
                dict(
                    stats[
                        cctv_id
                    ]
                )
            for cctv_id
            in test_ids
        }

    for cctv_id in test_ids:

        item = (
            final_stats[
                cctv_id
            ]
        )

        print()

        print(
            f"CCTV {cctv_id}"
        )

        print(
            f"  received      : "
            f"{item['received']}"
        )

        print(
            f"  sampled       : "
            f"{item['sampled']}"
        )

        print(
            f"  quality_good  : "
            f"{item['quality_good']}"
        )

        print(
            f"  quality_low   : "
            f"{item['quality_low']}"
        )

        print(
            f"  enqueued      : "
            f"{item['enqueued']}"
        )

        print(
            f"  queue_dropped : "
            f"{item['queue_dropped']}"
        )

        print(
            f"  yolo_results  : "
            f"{item['yolo_results']}"
        )

        print(
            f"  detections    : "
            f"{item['detections']}"
        )

    # =====================================================
    # 21. 핵심 검증
    # =====================================================

    for cctv_id in test_ids:

        item = (
            final_stats[
                cctv_id
            ]
        )

        if (
            item["received"]
            <= 0
        ):

            raise AssertionError(
                f"CCTV {cctv_id} "
                "Frame을 수신하지 못했습니다."
            )

        if (
            sampler.is_enabled(
                cctv_id
            )
            and item[
                "sampled"
            ]
            <= 0
        ):

            raise AssertionError(
                f"CCTV {cctv_id} "
                "Sampling이 발생하지 않았습니다."
            )

        if (
            item[
                "quality_good"
            ]
            <= 0
        ):

            raise AssertionError(
                f"CCTV {cctv_id}의 "
                "GOOD Quality Frame이 없습니다. "
                "영상 품질 또는 threshold를 "
                "확인해야 합니다."
            )

        if (
            item[
                "enqueued"
            ]
            <= 0
        ):

            raise AssertionError(
                f"CCTV {cctv_id}의 "
                "Frame이 YOLO Queue에 "
                "들어가지 않았습니다."
            )

        if (
            item[
                "yolo_results"
            ]
            <= 0
        ):

            raise AssertionError(
                f"CCTV {cctv_id}의 "
                "YOLO 결과가 없습니다."
            )

    if (
        manager.worker_count()
        != 0
    ):

        raise AssertionError(
            "종료 후 Capture Thread가 "
            "남아 있습니다."
        )

    print()
    print("=" * 80)

    print(
        "[SUCCESS] 실제 UTIC CCTV 2~3대 "
        "→ Sampling "
        "→ Quality "
        "→ 공용 AnalysisFrameQueue "
        "→ YoloWorker 병렬 Pipeline 정상"
    )

    print("=" * 80)


if __name__ == "__main__":
    main()