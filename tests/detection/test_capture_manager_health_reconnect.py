from __future__ import annotations

import time
from datetime import datetime
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from ai.contracts import Frame
from ai.detection.capture_manager import (
    CaptureWorkerManager,
)
from ai.detection.health_monitor import (
    CctvHealthMonitor,
)


KST = ZoneInfo(
    "Asia/Seoul"
)


# =========================================================
# 테스트 설정
# =========================================================

HEALTH_CHECK_INTERVAL_SEC = 0.1

STALE_AFTER_SEC = 0.5

WAIT_TIMEOUT_SEC = 5.0


# =========================================================
# Fake CaptureWorker
# =========================================================


class FakeCaptureWorker:
    """
    Health Monitor → CaptureWorkerManager
    → 특정 CCTV 재연결 전달 테스트용 Worker.

    실제 네트워크 / OpenCV는 사용하지 않는다.
    """

    def __init__(
        self,
        cctv_id: int,
    ) -> None:

        self.cctv_id = (
            cctv_id
        )

        self._stop_event = (
            Event()
        )

        self._reconnect_event = (
            Event()
        )

        self._lock = (
            Lock()
        )

        self.reconnect_request_count = (
            0
        )

    # =====================================================
    # Worker 실행
    # =====================================================

    def run(
        self,
        on_frame,
        on_status,
    ) -> None:

        # 최초 연결
        on_status(
            "CONNECTED"
        )

        try:

            while (
                not self._stop_event.is_set()
            ):

                # -----------------------------------------
                # 외부 재연결 요청 감지
                # -----------------------------------------

                if (
                    self._reconnect_event.wait(
                        timeout=0.05
                    )
                ):

                    self._reconnect_event.clear()

                    if (
                        self._stop_event.is_set()
                    ):
                        break

                    print(
                        f"[FAKE WORKER] "
                        f"CCTV {self.cctv_id} "
                        "재연결 처리"
                    )

                    on_status(
                        "RECONNECTING"
                    )

                    time.sleep(
                        0.05
                    )

                    on_status(
                        "CONNECTED"
                    )

        finally:

            on_status(
                "DISCONNECTED"
            )

    # =====================================================
    # 종료
    # =====================================================

    def stop(
        self,
    ) -> None:

        self._stop_event.set()

        self._reconnect_event.set()

    # =====================================================
    # 재연결 요청
    # =====================================================

    def request_reconnect(
        self,
    ) -> None:

        with self._lock:

            self.reconnect_request_count += 1

            current_count = (
                self.reconnect_request_count
            )

        print(
            f"[FAKE WORKER] "
            f"CCTV {self.cctv_id} "
            f"request_reconnect() "
            f"#{current_count}"
        )

        self._reconnect_event.set()


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
            0.05
        )

    raise TimeoutError(
        f"{description} "
        f"대기시간 초과 "
        f"({timeout_sec:.1f}초)"
    )


# =========================================================
# Main
# =========================================================


def main() -> None:

    print("=" * 78)

    print(
        "OCTV HEALTH MONITOR "
        "→ CAPTURE MANAGER "
        "TARGET RECONNECT TEST"
    )

    print("=" * 78)

    # =====================================================
    # 1. 테스트 CCTV
    # =====================================================

    cctvs = [
        {
            "id": 1,
            "name": "FAKE CCTV 1",
        },
        {
            "id": 2,
            "name": "FAKE CCTV 2",
        },
        {
            "id": 3,
            "name": "FAKE CCTV 3",
        },
    ]

    # =====================================================
    # 2. Fake Worker 보관
    # =====================================================

    workers: dict[
        int,
        FakeCaptureWorker,
    ] = {}

    worker_lock = Lock()

    # =====================================================
    # 3. 가짜 DB 상태
    # =====================================================

    state_lock = Lock()

    initial_time = (
        datetime.now(
            KST
        )
    )

    states = {
        1: {
            "id": 1,
            "connection_status":
                "DISCONNECTED",
            "last_frame_at":
                initial_time,
        },
        2: {
            "id": 2,
            "connection_status":
                "DISCONNECTED",
            "last_frame_at":
                initial_time,
        },
        3: {
            "id": 3,
            "connection_status":
                "DISCONNECTED",
            "last_frame_at":
                initial_time,
        },
    }

    # =====================================================
    # 4. Worker Factory
    # =====================================================

    def worker_factory(
        cctv,
    ) -> FakeCaptureWorker:

        cctv_id = int(
            cctv["id"]
        )

        worker = (
            FakeCaptureWorker(
                cctv_id=cctv_id,
            )
        )

        with worker_lock:

            workers[
                cctv_id
            ] = worker

        print(
            f"[FACTORY] "
            f"CCTV {cctv_id} "
            "Fake Worker 생성"
        )

        return worker

    # =====================================================
    # 5. Frame Callback
    #
    # 이번 테스트에서는 실제 Frame을
    # 사용하지 않는다.
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        pass

    # =====================================================
    # 6. Status Callback
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

        with state_lock:

            states[
                cctv_id
            ][
                "connection_status"
            ] = status

    # =====================================================
    # 7. CaptureWorkerManager
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

    # =====================================================
    # 8. Health Monitor State Provider
    # =====================================================

    def state_provider() -> list[
        dict
    ]:
        """
        CCTV 1, 3은 Frame이 계속 들어오는 것처럼
        last_frame_at을 갱신한다.

        CCTV 2만 last_frame_at을 멈춰서
        stale 상태를 만든다.
        """

        now = (
            datetime.now(
                KST
            )
        )

        with state_lock:

            # CCTV 1 정상
            states[
                1
            ][
                "last_frame_at"
            ] = now

            # CCTV 2는 의도적으로
            # last_frame_at 갱신하지 않음

            # CCTV 3 정상
            states[
                3
            ][
                "last_frame_at"
            ] = now

            return [
                dict(
                    states[1]
                ),
                dict(
                    states[2]
                ),
                dict(
                    states[3]
                ),
            ]

    # =====================================================
    # 9. Health Monitor → Manager 재연결 Callback
    # =====================================================

    reconnect_event = (
        Event()
    )

    def reconnect_requester(
        cctv_id: int,
    ) -> None:

        print(
            f"[HEALTH ACTION] "
            f"CCTV {cctv_id} "
            "재연결 요청"
        )

        requested = (
            manager.request_reconnect(
                cctv_id
            )
        )

        if not requested:

            raise RuntimeError(
                f"CCTV {cctv_id}의 "
                "실행 중 CaptureWorker를 "
                "찾을 수 없습니다."
            )

        reconnect_event.set()

    # =====================================================
    # 10. Health Monitor 생성
    # =====================================================

    health_monitor = (
        CctvHealthMonitor(
            check_interval_sec=(
                HEALTH_CHECK_INTERVAL_SEC
            ),
            stale_after_sec=(
                STALE_AFTER_SEC
            ),
        )
    )

    health_thread = Thread(
        target=(
            health_monitor.run
        ),
        kwargs={
            "state_provider":
                state_provider,

            "reconnect_requester":
                reconnect_requester,
        },
        name=(
            "capture-manager-"
            "health-test"
        ),
    )

    try:

        # =================================================
        # TEST 1
        # Worker 3개 시작
        # =================================================

        print()
        print(
            "[TEST 1] "
            "CCTV 3대 Worker 시작"
        )

        result = (
            manager.sync(
                cctvs
            )
        )

        print(
            f"sync result = "
            f"{result}"
        )

        wait_until(
            condition=lambda: (
                manager.running_cctv_ids()
                == [
                    1,
                    2,
                    3,
                ]
            ),
            timeout_sec=(
                WAIT_TIMEOUT_SEC
            ),
            description=(
                "CCTV 3대 Worker 실행"
            ),
        )

        def all_connected() -> bool:

            with state_lock:

                return all(
                    states[
                        cctv_id
                    ][
                        "connection_status"
                    ]
                    == "CONNECTED"
                    for cctv_id
                    in [
                        1,
                        2,
                        3,
                    ]
                )

        wait_until(
            condition=(
                all_connected
            ),
            timeout_sec=(
                WAIT_TIMEOUT_SEC
            ),
            description=(
                "CCTV 3대 CONNECTED"
            ),
        )

        print(
            "[PASS] "
            "CCTV 3대 CONNECTED"
        )

        # =================================================
        # TEST 2
        # Health Monitor 시작
        # =================================================

        print()
        print(
            "[TEST 2] "
            "Health Monitor 시작"
        )

        health_thread.start()

        # CCTV 2 stale 감지 대기
        if (
            not reconnect_event.wait(
                timeout=(
                    WAIT_TIMEOUT_SEC
                )
            )
        ):

            raise TimeoutError(
                "CCTV 2 stale "
                "재연결 요청이 "
                "발생하지 않았습니다."
            )

        # Worker가 재연결 상태 처리할 시간
        time.sleep(
            0.2
        )

        # =================================================
        # TEST 3
        # 어떤 CCTV에 요청됐는지 검증
        # =================================================

        print()
        print(
            "[TEST 3] "
            "재연결 대상 검증"
        )

        with worker_lock:

            reconnect_counts = {
                cctv_id:
                    workers[
                        cctv_id
                    ].reconnect_request_count
                for cctv_id
                in [
                    1,
                    2,
                    3,
                ]
            }

        print(
            f"reconnect_counts="
            f"{reconnect_counts}"
        )

        # CCTV 1은 정상
        if (
            reconnect_counts[
                1
            ]
            != 0
        ):

            raise AssertionError(
                "정상 CCTV 1에 "
                "재연결 요청이 발생했습니다."
            )

        # CCTV 2만 stale
        if (
            reconnect_counts[
                2
            ]
            != 1
        ):

            raise AssertionError(
                "stale CCTV 2에 "
                "재연결 요청이 정확히 "
                "1회 전달되지 않았습니다."
            )

        # CCTV 3은 정상
        if (
            reconnect_counts[
                3
            ]
            != 0
        ):

            raise AssertionError(
                "정상 CCTV 3에 "
                "재연결 요청이 발생했습니다."
            )

        print(
            "[PASS] "
            "CCTV 2에만 "
            "재연결 요청 전달"
        )

        # =================================================
        # TEST 4
        # 다른 CCTV Thread 유지 확인
        # =================================================

        print()
        print(
            "[TEST 4] "
            "다른 CCTV Thread 유지 확인"
        )

        running = (
            manager.running_cctv_ids()
        )

        print(
            f"running={running}"
        )

        if (
            running
            != [
                1,
                2,
                3,
            ]
        ):

            raise AssertionError(
                "CCTV 2 재연결 과정에서 "
                "다른 Capture Thread가 "
                "종료되었습니다."
            )

        print(
            "[PASS] "
            "CCTV 1,2,3 Thread 모두 유지"
        )

    finally:

        # =================================================
        # 정리
        # =================================================

        print()
        print(
            "[CLEANUP] "
            "Health Monitor 종료"
        )

        health_monitor.stop()

        if (
            health_thread.is_alive()
        ):

            health_thread.join(
                timeout=3
            )

        if (
            health_thread.is_alive()
        ):

            raise RuntimeError(
                "Health Monitor Thread가 "
                "종료되지 않았습니다."
            )

        print(
            "[CLEANUP] "
            "Capture Worker 전체 종료"
        )

        manager.stop_all()

    # =====================================================
    # 최종 확인
    # =====================================================

    if (
        manager.worker_count()
        != 0
    ):

        raise AssertionError(
            "종료 후 살아 있는 "
            "Capture Worker가 있습니다."
        )

    print()
    print("=" * 78)

    print(
        "[SUCCESS] "
        "Health Monitor "
        "→ CaptureWorkerManager "
        "→ 특정 CCTV Thread "
        "재연결 전달 정상"
    )

    print("=" * 78)


if __name__ == "__main__":
    main()