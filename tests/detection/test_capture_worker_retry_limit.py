"""CaptureWorker 최대 자동 재연결 횟수 테스트."""

import time

from threading import Event, Lock, Thread

import numpy as np

from ai.contracts import Frame
from ai.detection.capture_worker import CaptureWorker


# =========================================================
# 테스트용 VideoSource
# =========================================================

class FakeVideoSource:
    """
    연결 정책 테스트용 가짜 VideoSource.

    동작:
    1. 최초 연결은 성공
    2. 첫 Frame read에서 None 반환
       → 연결 중단 발생
    3. 자동 재연결 3회는 전부 실패
    4. 수동 재연결 요청 후에는 연결 성공
    """

    def __init__(
        self,
        cctv_id: int,
    ):
        self.cctv_id = cctv_id

        self.open_count = 0

        self.is_open = False

        self.manual_recovery_enabled = False

    def open(self) -> None:
        """
        최초 연결은 성공한다.

        이후 자동 재연결은 실패하고,
        manual_recovery_enabled=True가 된 뒤에는 성공한다.
        """

        self.open_count += 1

        print(
            f"[FAKE SOURCE] open() "
            f"호출 #{self.open_count}"
        )

        # 최초 연결
        if self.open_count == 1:

            self.is_open = True
            return

        # 수동 재연결 허용 후
        if self.manual_recovery_enabled:

            self.is_open = True
            return

        # 자동 재연결은 실패
        self.is_open = False

        raise ConnectionError(
            "테스트용 강제 연결 실패"
        )

    def read(self):
        """
        연결 성공 직후 Frame 수신 실패를 발생시킨다.
        """

        if not self.is_open:
            return None

        # 최초 정상 연결에서도 바로 장애 발생
        # 수동 복구 후에도 테스트 종료를 위해
        # 실제 Frame 하나를 반환한다.
        if self.manual_recovery_enabled:

            image = np.zeros(
                (100, 100, 3),
                dtype=np.uint8,
            )

            from datetime import datetime
            from zoneinfo import ZoneInfo

            return Frame(
                cctv_id=self.cctv_id,
                captured_at=datetime.now(
                    ZoneInfo("Asia/Seoul")
                ),
                image=image,
            )

        return None

    def get_fps(self) -> float:
        return 30.0

    def close(self) -> None:
        self.is_open = False


# =========================================================
# Main
# =========================================================

def main() -> None:

    print("=" * 70)

    print(
        "CAPTURE WORKER RETRY LIMIT TEST"
    )

    print("=" * 70)

    # -----------------------------------------------------
    # 테스트에서는 빠르게 보기 위해
    # 재연결 대기를 0.2초로 사용
    #
    # 실제 서비스 값은 DB에서 10초
    # -----------------------------------------------------

    reconnect_delay_sec = 0.2

    max_reconnect_attempts = 3

    worker = CaptureWorker(
        cctv_id=1,
        stream_url="fake://cctv-1",
        reconnect_delay_sec=(
            reconnect_delay_sec
        ),
        max_reconnect_attempts=(
            max_reconnect_attempts
        ),
        realtime_pacing=False,
    )

    fake_source = FakeVideoSource(
        cctv_id=1
    )

    # CaptureWorker가 내부에서 만든
    # 실제 VideoSource 대신 테스트용 Source 사용
    worker.source = fake_source

    # =====================================================
    # 상태 확인용 변수
    # =====================================================

    status_history: list[str] = []

    status_lock = Lock()

    disconnected_event = Event()

    reconnected_event = Event()

    frame_received_event = Event()

    connected_count = 0

    # =====================================================
    # Status Callback
    # =====================================================

    def handle_status(
        status: str,
    ) -> None:

        nonlocal connected_count

        print(
            f"[STATUS] {status}"
        )

        with status_lock:

            status_history.append(
                status
            )

            if status == "CONNECTED":

                connected_count += 1

                # 최초 CONNECTED가 아닌
                # 두 번째 CONNECTED면
                # 수동 복구 성공
                if connected_count >= 2:

                    reconnected_event.set()

            elif status == "DISCONNECTED":

                disconnected_event.set()

    # =====================================================
    # Frame Callback
    # =====================================================

    def handle_frame(
        frame: Frame,
    ) -> None:

        print(
            f"[FRAME] "
            f"CCTV {frame.cctv_id} "
            f"수신"
        )

        frame_received_event.set()

    # =====================================================
    # Worker 실행
    # =====================================================

    worker_thread = Thread(
        target=worker.run,
        kwargs={
            "on_frame":
                handle_frame,

            "on_status":
                handle_status,
        },
        name="capture-worker-retry-test",
    )

    worker_thread.start()

    # =====================================================
    # 1. 자동 재연결 3회 실패 후
    #    DISCONNECTED 확인
    # =====================================================

    print()

    print(
        "[1] 자동 재연결 실패 대기"
    )

    if not disconnected_event.wait(
        timeout=5
    ):

        worker.stop()

        worker_thread.join(
            timeout=2
        )

        raise AssertionError(
            "자동 재연결 3회 실패 후 "
            "DISCONNECTED 상태가 되지 않았습니다."
        )

    print()

    print(
        "[PASS] 자동 재연결 제한 도달"
    )

    # -----------------------------------------------------
    # 최초 연결 1회 +
    # 자동 재연결 3회
    #
    # 총 open() = 4회여야 함
    # -----------------------------------------------------

    expected_open_count = (
        1
        + max_reconnect_attempts
    )

    print(
        f"open() 호출 수      : "
        f"{fake_source.open_count}"
    )

    print(
        f"예상 open() 호출 수 : "
        f"{expected_open_count}"
    )

    if (
        fake_source.open_count
        != expected_open_count
    ):

        worker.stop()

        worker_thread.join(
            timeout=2
        )

        raise AssertionError(
            "자동 재연결 횟수가 "
            "설정값과 일치하지 않습니다."
        )

    # =====================================================
    # 2. DISCONNECTED 후에도
    #    Worker Thread가 살아있는지 확인
    # =====================================================

    if not worker_thread.is_alive():

        raise AssertionError(
            "최대 재연결 실패 후 "
            "Worker Thread가 종료되었습니다."
        )

    print(
        "[PASS] DISCONNECTED 상태에서도 "
        "Worker Thread 유지"
    )

    # =====================================================
    # 3. 수동 재연결 요청
    # =====================================================

    print()

    print(
        "[2] 수동 재연결 요청"
    )

    # 이제부터 open() 성공 허용
    fake_source.manual_recovery_enabled = True

    worker.request_reconnect()

    if not reconnected_event.wait(
        timeout=3
    ):

        worker.stop()

        worker_thread.join(
            timeout=2
        )

        raise AssertionError(
            "수동 재연결 요청 후 "
            "CONNECTED 상태로 복구되지 않았습니다."
        )

    print(
        "[PASS] 수동 재연결 후 CONNECTED"
    )

    # =====================================================
    # 4. 실제 Frame 전달 확인
    # =====================================================

    if not frame_received_event.wait(
        timeout=2
    ):

        worker.stop()

        worker_thread.join(
            timeout=2
        )

        raise AssertionError(
            "수동 복구 후 Frame이 "
            "수신되지 않았습니다."
        )

    print(
        "[PASS] 수동 복구 후 Frame 수신"
    )

    # =====================================================
    # 5. Worker 종료
    # =====================================================

    worker.stop()

    worker_thread.join(
        timeout=3
    )

    if worker_thread.is_alive():

        raise AssertionError(
            "CaptureWorker Thread가 "
            "종료되지 않았습니다."
        )

    # =====================================================
    # 결과
    # =====================================================

    with status_lock:

        final_status_history = (
            status_history.copy()
        )

    print()

    print("=" * 70)

    print("RESULT")

    print("=" * 70)

    print(
        f"Max reconnect attempts : "
        f"{max_reconnect_attempts}"
    )

    print(
        f"최종 open() 호출 수     : "
        f"{fake_source.open_count}"
    )

    print(
        "상태 History            : "
        + " → ".join(
            final_status_history
        )
    )

    print()

    print(
        "[SUCCESS] "
        "최대 자동 재연결 횟수 제한 "
        "+ DISCONNECTED 대기 "
        "+ 수동 재연결 복구 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()