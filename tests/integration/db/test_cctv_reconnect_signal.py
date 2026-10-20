from __future__ import annotations

import time
from threading import (
    Event,
    Thread,
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


TEST_CCTV_ID = 987654321

TEST_TIMEOUT_SEC = 5.0


def main() -> None:

    print("=" * 70)
    print(
        "OCTV CCTV MANUAL RECONNECT "
        "LISTEN / NOTIFY TEST"
    )
    print("=" * 70)

    stop_event = Event()

    received_event = Event()

    received_ids: list[int] = []

    # =====================================================
    # Runtime 쪽 reconnect requester 대역
    # =====================================================

    def reconnect_requester(
        cctv_id: int,
    ) -> None:

        print(
            "[TEST CALLBACK] "
            f"reconnect_requester({cctv_id})"
        )

        received_ids.append(
            cctv_id
        )

        received_event.set()

        # 첫 요청을 받았으면
        # Listener를 종료시킨다.
        stop_event.set()

    # =====================================================
    # Listener 생성
    # =====================================================

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
            "test-reconnect-listener"
        ),
    )

    print()
    print(
        "[1] Listener Thread 시작"
    )

    listener_thread.start()

    # =====================================================
    # PostgreSQL NOTIFY 전송
    #
    # Listener가 LISTEN을 완료하기 전에
    # 첫 NOTIFY가 전송될 가능성이 있으므로,
    # 수신될 때까지 짧은 간격으로 재시도한다.
    # =====================================================

    deadline = (
        time.monotonic()
        + TEST_TIMEOUT_SEC
    )

    attempt = 0

    try:

        while not received_event.is_set():

            attempt += 1

            print(
                "[2] NOTIFY 전송 "
                f"attempt={attempt} "
                f"/ cctv_id={TEST_CCTV_ID}"
            )

            with get_connection() as connection:

                publish_reconnect_request(
                    connection,
                    TEST_CCTV_ID,
                )

            if received_event.wait(
                0.25
            ):
                break

            if (
                time.monotonic()
                >= deadline
            ):

                raise TimeoutError(
                    "PostgreSQL NOTIFY가 "
                    f"{TEST_TIMEOUT_SEC:.1f}초 내에 "
                    "Listener로 전달되지 않았습니다."
                )

    finally:

        stop_event.set()

        listener_thread.join(
            timeout=3.0
        )

    # =====================================================
    # 결과 검증
    # =====================================================

    if listener_thread.is_alive():

        raise AssertionError(
            "Reconnect Listener Thread가 "
            "종료되지 않았습니다."
        )

    if not received_event.is_set():

        raise AssertionError(
            "Reconnect 요청을 "
            "수신하지 못했습니다."
        )

    if TEST_CCTV_ID not in received_ids:

        raise AssertionError(
            "수신된 CCTV ID가 다릅니다. "
            f"expected={TEST_CCTV_ID} "
            f"/ actual={received_ids}"
        )

    print()
    print(
        "[PASS] PostgreSQL NOTIFY "
        "→ Reconnect Listener "
        "→ reconnect_requester 전달 성공"
    )

    print(
        f"[PASS] received_ids="
        f"{received_ids}"
    )

    print("=" * 70)


if __name__ == "__main__":

    main()