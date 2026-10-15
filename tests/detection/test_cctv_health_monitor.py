"""CCTV Health Monitor 동작 테스트."""

import time
from datetime import datetime
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from ai.detection.health_monitor import (
    CctvHealthMonitor,
)


KST = ZoneInfo("Asia/Seoul")


# =========================================================
# 테스트 설정
# =========================================================

CHECK_INTERVAL_SEC = 0.1

STALE_AFTER_SEC = 0.5


# =========================================================
# Main
# =========================================================

def main() -> None:

    print("=" * 70)
    print("OCTV CCTV HEALTH MONITOR TEST")
    print("=" * 70)

    # =====================================================
    # 가짜 CCTV 상태
    #
    # 실제 DB 대신
    # 메모리에 CCTV 상태 하나를 만들어 사용한다.
    # =====================================================

    state_lock = Lock()

    fake_state = {
        "id": 1,
        "connection_status": "CONNECTED",
        "last_frame_at": datetime.now(KST),
    }

    # =====================================================
    # 재연결 요청 기록
    # =====================================================

    reconnect_lock = Lock()

    reconnect_count = 0

    reconnect_event = Event()

    # =====================================================
    # Health Monitor에 제공할 상태 조회 함수
    # =====================================================

    def state_provider() -> list[dict]:
        """
        실제 환경에서는 DB에서 CCTV 상태를 조회하지만
        이 테스트에서는 fake_state를 반환한다.
        """

        with state_lock:

            return [
                fake_state.copy()
            ]

    # =====================================================
    # Health Monitor가 재연결을 요청했을 때 호출되는 함수
    # =====================================================

    def reconnect_requester(
        cctv_id: int,
    ) -> None:

        nonlocal reconnect_count

        with reconnect_lock:

            reconnect_count += 1

            current_count = (
                reconnect_count
            )

        print(
            f"[TEST RECONNECT] "
            f"CCTV {cctv_id} "
            f"재연결 요청 #{current_count}"
        )

        reconnect_event.set()

    # =====================================================
    # 테스트용 현재 reconnect_count 조회
    # =====================================================

    def get_reconnect_count() -> int:

        with reconnect_lock:
            return reconnect_count

    # =====================================================
    # 가짜 Frame 수신
    #
    # 실제로는 CaptureWorker가 Frame을 받고
    # DB의 last_frame_at을 갱신한다.
    #
    # 여기서는 직접 시각만 변경한다.
    # =====================================================

    def simulate_frame() -> None:

        with state_lock:

            fake_state[
                "last_frame_at"
            ] = datetime.now(KST)

            current = (
                fake_state[
                    "last_frame_at"
                ]
            )

        print(
            f"[TEST FRAME] "
            f"last_frame_at 갱신 "
            f"→ {current.strftime('%H:%M:%S.%f')[:-3]}"
        )

    # =====================================================
    # Health Monitor 생성
    # =====================================================

    monitor = CctvHealthMonitor(
        check_interval_sec=(
            CHECK_INTERVAL_SEC
        ),
        stale_after_sec=(
            STALE_AFTER_SEC
        ),
    )

    monitor_thread = Thread(
        target=monitor.run,
        kwargs={
            "state_provider":
                state_provider,

            "reconnect_requester":
                reconnect_requester,
        },
        name="cctv-health-monitor-test",
    )

    # =====================================================
    # Health Monitor 시작
    # =====================================================

    print()
    print(
        "[1] Health Monitor 시작"
    )

    monitor_thread.start()

    # 처음 CONNECTED 상태를 관찰할 시간
    time.sleep(0.2)

    # =====================================================
    # TEST 1
    #
    # Frame이 계속 들어오면
    # 재연결 요청이 없어야 한다.
    # =====================================================

    print()
    print(
        "[2] 정상 Frame 갱신 테스트"
    )

    for _ in range(4):

        simulate_frame()

        # STALE 0.5초보다 짧은 간격으로 갱신
        time.sleep(0.2)

    normal_reconnect_count = (
        get_reconnect_count()
    )

    print(
        f"현재 재연결 요청 수 : "
        f"{normal_reconnect_count}"
    )

    if normal_reconnect_count != 0:

        raise AssertionError(
            "Frame이 정상적으로 갱신 중인데 "
            "재연결 요청이 발생했습니다."
        )

    print(
        "[PASS] 정상 Frame 수신 중 "
        "재연결 요청 없음"
    )

    # =====================================================
    # TEST 2
    #
    # Frame 갱신을 멈춘다.
    #
    # 0.5초 이상 변화가 없으면
    # 재연결 요청이 1번 발생해야 한다.
    # =====================================================

    print()
    print(
        "[3] STALE Frame 감지 테스트"
    )

    print(
        "Frame 갱신을 중단합니다."
    )

    reconnect_event.clear()

    detected = reconnect_event.wait(
        timeout=2.0
    )

    if not detected:

        raise AssertionError(
            "Frame 갱신이 중단됐는데 "
            "Health Monitor가 "
            "재연결 요청을 하지 않았습니다."
        )

    first_reconnect_count = (
        get_reconnect_count()
    )

    print(
        f"현재 재연결 요청 수 : "
        f"{first_reconnect_count}"
    )

    if first_reconnect_count != 1:

        raise AssertionError(
            "첫 STALE 상태에서 "
            "재연결 요청이 정확히 "
            "1번 발생하지 않았습니다."
        )

    print(
        "[PASS] STALE Frame 감지 "
        "→ 재연결 요청 1회"
    )

    # =====================================================
    # TEST 3
    #
    # 계속 stale 상태라도
    # 같은 장애에 대해 재연결 요청을
    # 반복하면 안 된다.
    # =====================================================

    print()
    print(
        "[4] 중복 재연결 방지 테스트"
    )

    # stale 상태 그대로 유지
    time.sleep(
        STALE_AFTER_SEC
        + 0.4
    )

    duplicate_count = (
        get_reconnect_count()
    )

    print(
        f"현재 재연결 요청 수 : "
        f"{duplicate_count}"
    )

    if duplicate_count != 1:

        raise AssertionError(
            "같은 STALE 상태에서 "
            "재연결 요청이 중복 발생했습니다."
        )

    print(
        "[PASS] 동일 STALE 상태에서 "
        "중복 재연결 없음"
    )

    # =====================================================
    # TEST 4
    #
    # Frame이 다시 들어오면 정상 복구.
    #
    # 그 뒤 다시 Frame이 멈추면
    # 새로운 장애로 보고 재연결 요청이
    # 다시 가능해야 한다.
    # =====================================================

    print()
    print(
        "[5] 복구 후 재장애 테스트"
    )

    print(
        "Frame 수신 복구"
    )

    simulate_frame()

    # Health Monitor가 변경된 last_frame_at을
    # 확인할 시간을 준다.
    time.sleep(0.3)

    # 정상 수신임을 한 번 더 명확하게 갱신
    simulate_frame()

    time.sleep(0.2)

    print(
        "다시 Frame 갱신 중단"
    )

    reconnect_event.clear()

    second_detected = (
        reconnect_event.wait(
            timeout=2.0
        )
    )

    if not second_detected:

        raise AssertionError(
            "Frame 복구 후 다시 발생한 "
            "STALE 상태를 감지하지 못했습니다."
        )

    second_reconnect_count = (
        get_reconnect_count()
    )

    print(
        f"현재 재연결 요청 수 : "
        f"{second_reconnect_count}"
    )

    if second_reconnect_count != 2:

        raise AssertionError(
            "복구 후 새로운 STALE 상태에서 "
            "두 번째 재연결 요청이 "
            "정확히 발생하지 않았습니다."
        )

    print(
        "[PASS] 복구 후 새로운 STALE 감지 "
        "→ 재연결 요청 가능"
    )

    # =====================================================
    # 종료
    # =====================================================

    print()
    print(
        "[6] Health Monitor 종료"
    )

    monitor.stop()

    monitor_thread.join(
        timeout=3
    )

    if monitor_thread.is_alive():

        raise AssertionError(
            "Health Monitor Thread가 "
            "정상 종료되지 않았습니다."
        )

    # =====================================================
    # 결과
    # =====================================================

    print()
    print("=" * 70)
    print("RESULT")
    print("=" * 70)

    print(
        f"최종 재연결 요청 수 : "
        f"{get_reconnect_count()}"
    )

    print()

    print(
        "[SUCCESS] "
        "CCTV Health Monitor "
        "동작 테스트 정상"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()