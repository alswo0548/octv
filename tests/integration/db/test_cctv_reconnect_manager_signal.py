from __future__ import annotations

import time
from threading import (
    Event,
    Lock,
    Thread,
)

from ai.detection.capture_manager import (
    CaptureWorkerManager,
)
from ai.detection.reconnect_listener import (
    CctvReconnectListener,
)
from backend.app.cctvs.reconnect_signal import (
    publish_reconnect_request,
)
from backend.app.db.session import (
    get_connection,
)


TEST_CCTV_ID = 987654322

TEST_TIMEOUT_SEC = 5.0


class FakeReconnectWorker:
    """
    실제 CCTV 연결 없이
    CaptureWorkerManager의 reconnect 전달만 검증한다.
    """

    def __init__(
        self,
        cctv_id: int,
    ) -> None:

        self.cctv_id = cctv_id

        self._stop_event = Event()

        self.reconnect_event = Event()

        self._lock = Lock()

        self.reconnect_count = 0

    def run(
        self,
        on_frame,
        on_status,
    ) -> None:

        on_status(
            "CONNECTED"
        )

        try:

            while not self._stop_event.wait(
                0.1
            ):
                pass

        finally:

            on_status(
                "DISCONNECTED"
            )

    def stop(
        self,
    ) -> None:

        self._stop_event.set()

    def request_reconnect(
        self,
    ) -> None:

        with self._lock:

            self.reconnect_count += 1

            count = (
                self.reconnect_count
            )

        print(
            "[FAKE WORKER] "
            f"CCTV {self.cctv_id} "
            f"request_reconnect() "
            f"#{count}"
        )

        self.reconnect_event.set()


def main() -> None:

    print("=" * 70)
    print(
        "OCTV CCTV MANUAL RECONNECT "
        "MANAGER SIGNAL TEST"
    )
    print("=" * 70)

    stop_event = Event()

    workers: dict[
        int,
        FakeReconnectWorker,
    ] = {}

    # =====================================================
    # Fake Worker Factory
    # =====================================================

    def worker_factory(
        cctv,
    ) -> FakeReconnectWorker:

        cctv_id = int(
            cctv["id"]
        )

        worker = (
            FakeReconnectWorker(
                cctv_id
            )
        )

        workers[
            cctv_id
        ] = worker

        return worker

    # =====================================================
    # Manager Callback
    # =====================================================

    def handle_frame(
        frame,
    ) -> None:

        return

    def handle_status(
        cctv_id: int,
        status: str,
    ) -> None:

        print(
            "[MANAGER STATUS] "
            f"CCTV {cctv_id} "
            f"→ {status}"
        )

    # =====================================================
    # CaptureWorkerManager
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

    listener_thread: (
        Thread | None
    ) = None

    try:

        # =================================================
        # 1. Fake CCTV Worker 시작
        # =================================================

        print()
        print(
            "[1] Fake CCTV Worker 시작"
        )

        result = manager.sync(
            [
                {
                    "id": TEST_CCTV_ID,
                    "name": (
                        "MANUAL RECONNECT TEST"
                    ),
                    "provider": "TEST",
                },
            ]
        )

        print(
            f"sync result={result}"
        )

        if (
            TEST_CCTV_ID
            not in manager.running_cctv_ids()
        ):

            raise AssertionError(
                "테스트 CCTV Worker가 "
                "시작되지 않았습니다."
            )

        worker = workers[
            TEST_CCTV_ID
        ]

        # =================================================
        # 2. Listener callback
        #
        # 실제 Runtime의 _request_reconnect()와
        # 동일한 방식으로 Manager에 전달한다.
        # =================================================

        def reconnect_requester(
            cctv_id: int,
        ) -> None:

            print(
                "[TEST RUNTIME] "
                f"Manager reconnect 요청 "
                f"/ CCTV {cctv_id}"
            )

            requested = (
                manager.request_reconnect(
                    cctv_id
                )
            )

            if not requested:

                raise RuntimeError(
                    f"CCTV {cctv_id}의 "
                    "실행 중 Worker가 없습니다."
                )

        listener = (
            CctvReconnectListener(
                stop_event=(
                    stop_event
                ),
                reconnect_requester=(
                    reconnect_requester
                ),
            )
        )

        listener_thread = Thread(
            target=(
                listener.run
            ),
            name=(
                "test-reconnect-manager-listener"
            ),
        )

        print()
        print(
            "[2] PostgreSQL Listener 시작"
        )

        listener_thread.start()

        # =================================================
        # 3. PostgreSQL NOTIFY
        # =================================================

        deadline = (
            time.monotonic()
            + TEST_TIMEOUT_SEC
        )

        attempt = 0

        while not worker.reconnect_event.is_set():

            attempt += 1

            print(
                "[3] NOTIFY 전송 "
                f"attempt={attempt} "
                f"/ cctv_id="
                f"{TEST_CCTV_ID}"
            )

            with get_connection() as connection:

                publish_reconnect_request(
                    connection,
                    TEST_CCTV_ID,
                )

            if worker.reconnect_event.wait(
                0.25
            ):
                break

            if (
                time.monotonic()
                >= deadline
            ):

                raise TimeoutError(
                    "수동 재연결 요청이 "
                    f"{TEST_TIMEOUT_SEC:.1f}초 내에 "
                    "Worker까지 전달되지 않았습니다."
                )

        # =================================================
        # 4. 결과 검증
        # =================================================

        if (
            worker.reconnect_count
            < 1
        ):

            raise AssertionError(
                "Fake Worker의 "
                "request_reconnect()가 "
                "호출되지 않았습니다."
            )

        print()
        print(
            "[PASS] PostgreSQL NOTIFY"
        )

        print(
            "[PASS] "
            "CctvReconnectListener"
        )

        print(
            "[PASS] "
            "CaptureWorkerManager."
            "request_reconnect()"
        )

        print(
            "[PASS] "
            "Fake Worker."
            "request_reconnect()"
        )

        print(
            "[PASS] "
            f"reconnect_count="
            f"{worker.reconnect_count}"
        )

    finally:

        stop_event.set()

        if listener_thread is not None:

            listener_thread.join(
                timeout=3.0
            )

        manager.stop_all()

    if (
        listener_thread is not None
        and listener_thread.is_alive()
    ):

        raise AssertionError(
            "Reconnect Listener Thread가 "
            "종료되지 않았습니다."
        )

    print("=" * 70)


if __name__ == "__main__":

    main()