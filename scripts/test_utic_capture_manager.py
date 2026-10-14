from __future__ import annotations

import time
from threading import Lock

from ai.contracts import Frame
from ai.detection.capture_manager import CaptureWorkerManager
from ai.detection.capture_worker import CaptureWorker

from backend.app.cctvs.repository import (
    list_monitored_utic_cctvs,
    update_connection_status,
    update_last_frame_at,
)
from backend.app.db.session import get_connection
from backend.app.settings.repository import get_monitoring_settings

# 기존 단일 UTIC 통합 테스트에서 이미 검증한
# UTIC 인증 / Stream URL 조회 로직 재사용
from scripts.test_utic_capture_worker import (
    get_utic_stream_url,
)


# =========================================================
# 테스트 설정
# =========================================================

TEST_CCTV_COUNT = 3
MIN_REQUIRED_CCTV_COUNT = 2

INITIAL_CONNECT_TIMEOUT_SEC = 60.0
FRAME_RECEIVE_TIMEOUT_SEC = 30.0

PARALLEL_RUN_SEC = 8.0
MIN_FRAMES_PER_CCTV = 3

LAST_FRAME_DB_INTERVAL_SEC = 5.0


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

        time.sleep(0.1)

    raise TimeoutError(
        f"{description} 대기시간을 초과했습니다. "
        f"timeout={timeout_sec:.1f}s"
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print("=" * 78)
    print(
        "OCTV REAL UTIC "
        "MULTI-CCTV CAPTURE MANAGER TEST"
    )
    print("=" * 78)

    # =====================================================
    # 1. DB 감시 대상 CCTV 조회
    # =====================================================

    with get_connection() as connection:

        monitored_cctvs = (
            list_monitored_utic_cctvs(
                connection
            )
        )

    print()
    print(
        f"[1] 감시 대상 UTIC CCTV 수 : "
        f"{len(monitored_cctvs)}"
    )

    if monitored_cctvs:

        for cctv in monitored_cctvs[:10]:

            print(
                f"  - id={cctv['id']} "
                f"/ external="
                f"{cctv['external_cctv_id']} "
                f"/ name={cctv['name']} "
                f"/ mode="
                f"{cctv['monitored_mode']}"
            )

    if (
        len(monitored_cctvs)
        < MIN_REQUIRED_CCTV_COUNT
    ):

        raise RuntimeError(
            "\n실제 병렬 테스트에는 "
            "감시 대상 UTIC CCTV가 "
            f"최소 {MIN_REQUIRED_CCTV_COUNT}대 "
            "필요합니다.\n"
            "현재 cctvs.is_monitored=TRUE 인 "
            "UTIC CCTV를 2~3대로 만든 뒤 "
            "다시 실행하세요."
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
        int(cctv["id"])
        for cctv in test_cctvs
    ]

    print()
    print(
        f"[TEST TARGET] "
        f"{len(test_cctvs)}대 "
        f"/ IDs={test_ids}"
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
    print("[2] Capture 설정")

    print(
        f"Reconnect interval     : "
        f"{reconnect_interval_sec:.1f}s"
    )

    print(
        f"Max reconnect attempts : "
        f"{max_reconnect_attempts}"
    )

    # =====================================================
    # 3. 테스트 상태
    # =====================================================

    frame_lock = Lock()
    status_lock = Lock()
    heartbeat_lock = Lock()

    frame_counts: dict[
        int,
        int,
    ] = {}

    status_history: dict[
        int,
        list[str],
    ] = {}

    last_frame_db_update_at: dict[
        int,
        float,
    ] = {}

    # =====================================================
    # 4. Worker Factory
    #
    # 실행 프로세스 / Manager는 하나.
    #
    # CCTV마다:
    # CaptureWorker 객체 1개
    # + Capture Thread 1개
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

        print(
            f"[FACTORY] "
            f"CCTV {cctv_id} "
            "CaptureWorker 생성"
        )

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
    # 5. Status Callback
    # =====================================================

    def handle_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            f"[STATUS] "
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
                f"/ {exc}"
            )

    # =====================================================
    # 6. Frame Callback
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        cctv_id = int(
            frame.cctv_id
        )

        # ---------------------------------------------
        # CCTV별 Frame Count
        # ---------------------------------------------

        with frame_lock:

            current_count = (
                frame_counts.get(
                    cctv_id,
                    0,
                )
                + 1
            )

            frame_counts[
                cctv_id
            ] = current_count

        # ---------------------------------------------
        # CCTV별 DB Heartbeat
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
                    f"/ {exc}"
                )

        # 너무 많은 로그 방지
        if (
            current_count == 1
            or current_count % 100 == 0
        ):

            print(
                f"[FRAME] "
                f"CCTV {cctv_id} "
                f"/ count={current_count} "
                f"/ shape="
                f"{frame.image.shape} "
                f"/ captured_at="
                f"{frame.captured_at}"
            )

    # =====================================================
    # 7. CaptureWorkerManager 1개 생성
    # =====================================================

    manager = (
        CaptureWorkerManager(
            worker_factory=(
                worker_factory
            ),
            on_frame=(
                handle_frame
            ),
            on_status=(
                handle_status
            ),
        )
    )

    try:

        # =================================================
        # 8. 실제 CCTV 동시 시작
        # =================================================

        print()
        print(
            "[3] "
            "CaptureWorkerManager.sync() "
            "→ 실제 UTIC CCTV 동시 시작"
        )

        result = (
            manager.sync(
                test_cctvs
            )
        )

        print(
            f"sync result = {result}"
        )

        if (
            sorted(
                result["started"]
            )
            != sorted(
                test_ids
            )
        ):

            raise AssertionError(
                "시작된 CCTV 목록이 "
                "예상과 다릅니다. "
                f"expected={test_ids}, "
                f"actual="
                f"{result['started']}"
            )

        # =================================================
        # 9. 모든 CCTV CONNECTED 확인
        # =================================================

        print()
        print(
            "[4] 모든 CCTV "
            "CONNECTED 대기"
        )

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
                "모든 실제 UTIC CCTV "
                "CONNECTED"
            ),
        )

        print(
            "[PASS] "
            "모든 CCTV CONNECTED"
        )

        # =================================================
        # 10. 모든 CCTV Frame 수신 확인
        # =================================================

        print()
        print(
            "[5] CCTV별 "
            "Frame 동시 수신 대기"
        )

        def all_have_frames() -> bool:

            with frame_lock:

                return all(
                    frame_counts.get(
                        cctv_id,
                        0,
                    )
                    >= MIN_FRAMES_PER_CCTV
                    for cctv_id
                    in test_ids
                )

        wait_until(
            condition=(
                all_have_frames
            ),
            timeout_sec=(
                FRAME_RECEIVE_TIMEOUT_SEC
            ),
            description=(
                "모든 실제 UTIC CCTV "
                "Frame 수신"
            ),
        )

        with frame_lock:

            before_counts = {
                cctv_id:
                    frame_counts.get(
                        cctv_id,
                        0,
                    )
                for cctv_id
                in test_ids
            }

        print(
            "[PASS] "
            "모든 CCTV Frame 수신"
        )

        print(
            f"frame_counts="
            f"{before_counts}"
        )

        # =================================================
        # 11. 병렬 수신 지속 확인
        # =================================================

        print()
        print(
            f"[6] "
            f"{PARALLEL_RUN_SEC:.1f}초 동안 "
            "병렬 수신 유지 확인"
        )

        time.sleep(
            PARALLEL_RUN_SEC
        )

        with frame_lock:

            after_counts = {
                cctv_id:
                    frame_counts.get(
                        cctv_id,
                        0,
                    )
                for cctv_id
                in test_ids
            }

        print(
            f"before={before_counts}"
        )

        print(
            f"after ={after_counts}"
        )

        for cctv_id in test_ids:

            if (
                after_counts[
                    cctv_id
                ]
                <= before_counts[
                    cctv_id
                ]
            ):

                raise AssertionError(
                    f"CCTV {cctv_id}의 "
                    "Frame이 병렬 실행 중 "
                    "증가하지 않았습니다."
                )

        running = (
            manager.running_cctv_ids()
        )

        if (
            running
            != sorted(
                test_ids
            )
        ):

            raise AssertionError(
                "실행 중 CCTV 목록이 "
                "예상과 다릅니다. "
                f"expected="
                f"{sorted(test_ids)}, "
                f"actual={running}"
            )

        print(
            "[PASS] "
            "모든 CCTV Thread "
            "병렬 수신 지속"
        )

    finally:

        # =================================================
        # 12. 전체 종료
        # =================================================

        print()
        print(
            "[7] 전체 Capture Thread 종료"
        )

        manager.stop_all()

    # =====================================================
    # 13. 최종 종료 검증
    # =====================================================

    if (
        manager.worker_count()
        != 0
    ):

        raise AssertionError(
            "종료 후 살아 있는 "
            "CaptureWorker Thread가 있습니다."
        )

    with status_lock:

        final_status_history = {
            cctv_id:
                list(
                    status_history.get(
                        cctv_id,
                        [],
                    )
                )
            for cctv_id
            in test_ids
        }

    with frame_lock:

        final_frame_counts = {
            cctv_id:
                frame_counts.get(
                    cctv_id,
                    0,
                )
            for cctv_id
            in test_ids
        }

    print()
    print("[STATUS HISTORY]")

    for cctv_id in test_ids:

        print(
            f"CCTV {cctv_id} : "
            + " → ".join(
                final_status_history[
                    cctv_id
                ]
            )
        )

        if (
            not final_status_history[
                cctv_id
            ]
            or final_status_history[
                cctv_id
            ][-1]
            != "DISCONNECTED"
        ):

            raise AssertionError(
                f"CCTV {cctv_id} "
                "종료 상태가 "
                "DISCONNECTED가 아닙니다."
            )

    print()
    print("[FRAME COUNTS]")

    for cctv_id in test_ids:

        print(
            f"CCTV {cctv_id} : "
            f"{final_frame_counts[cctv_id]}"
        )

        if (
            final_frame_counts[
                cctv_id
            ]
            < MIN_FRAMES_PER_CCTV
        ):

            raise AssertionError(
                f"CCTV {cctv_id} "
                "Frame 수가 "
                "기준보다 적습니다."
            )

    print()
    print("=" * 78)

    print(
        "[SUCCESS] "
        "실제 UTIC CCTV 2~3대 "
        "CaptureWorkerManager "
        "병렬 Thread 수집 정상"
    )

    print("=" * 78)


if __name__ == "__main__":
    main()