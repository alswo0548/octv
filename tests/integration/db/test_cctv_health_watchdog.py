from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ai.detection.health import (
    calculate_frame_age_sec,
    is_frame_stale,
    should_reconnect_cctv,
)

from backend.app.cctvs.repository import (
    get_cctv_runtime_state,
    list_monitored_utic_cctvs,
)

from backend.app.db.session import (
    get_connection,
)


KST = ZoneInfo("Asia/Seoul")

STALE_AFTER_SEC = 20.0


def main() -> None:
    print("=" * 70)
    print("OCTV CCTV HEALTH WATCHDOG TEST")
    print("=" * 70)

    # =====================================================
    # 1. 테스트 대상 CCTV 조회
    # =====================================================

    with get_connection() as connection:
        cctvs = list_monitored_utic_cctvs(
            connection
        )

    if not cctvs:
        raise RuntimeError(
            "감시 대상 UTIC CCTV가 없습니다."
        )

    cctv_id = cctvs[0]["id"]

    # =====================================================
    # 2. 실제 DB 상태 확인
    # =====================================================

    with get_connection() as connection:
        state = get_cctv_runtime_state(
            connection,
            cctv_id,
        )

    age_sec = calculate_frame_age_sec(
        state["last_frame_at"]
    )

    stale = is_frame_stale(
        last_frame_at=(
            state["last_frame_at"]
        ),
        stale_after_sec=(
            STALE_AFTER_SEC
        ),
    )

    print()
    print("[1] 실제 DB 상태")

    print(
        f"CCTV ID              : "
        f"{state['id']}"
    )

    print(
        f"External CCTV ID     : "
        f"{state['external_cctv_id']}"
    )

    print(
        f"connection_status    : "
        f"{state['connection_status']}"
    )

    print(
        f"last_frame_at        : "
        f"{state['last_frame_at']}"
    )

    if age_sec is None:
        print(
            "last_frame_age      : "
            "아직 Frame 없음"
        )

    else:
        print(
            f"last_frame_age      : "
            f"{age_sec:.2f} sec"
        )

    print(
        f"stale_after         : "
        f"{STALE_AFTER_SEC:.1f} sec"
    )

    print(
        f"is_stale            : "
        f"{stale}"
    )

    # =====================================================
    # 3. Fresh Frame 가상 테스트
    # =====================================================

    now = datetime.now(KST)

    fresh_frame_at = (
        now
        - timedelta(
            seconds=5
        )
    )

    fresh_result = is_frame_stale(
        last_frame_at=fresh_frame_at,
        stale_after_sec=(
            STALE_AFTER_SEC
        ),
        now=now,
    )

    print()
    print("[2] 최근 Frame 테스트")

    print(
        "마지막 Frame        : "
        "5초 전"
    )

    print(
        f"is_stale            : "
        f"{fresh_result}"
    )

    if fresh_result:
        raise AssertionError(
            "5초 전 Frame이 stale로 "
            "판정되었습니다."
        )

    # =====================================================
    # 4. Stale Frame 가상 테스트
    # =====================================================

    stale_frame_at = (
        now
        - timedelta(
            seconds=25
        )
    )

    stale_result = is_frame_stale(
        last_frame_at=stale_frame_at,
        stale_after_sec=(
            STALE_AFTER_SEC
        ),
        now=now,
    )

    print()
    print("[3] 오래된 Frame 테스트")

    print(
        "마지막 Frame        : "
        "25초 전"
    )

    print(
        f"is_stale            : "
        f"{stale_result}"
    )

    if not stale_result:
        raise AssertionError(
            "25초 전 Frame이 stale로 "
            "판정되지 않았습니다."
        )

    # =====================================================
    # 5. 재연결 판단 테스트
    # =====================================================

    print()
    print("[4] 재연결 판단 테스트")

    connected_fresh = should_reconnect_cctv(
        connection_status="CONNECTED",
        last_frame_at=(
            now
            - timedelta(seconds=5)
        ),
        stale_after_sec=STALE_AFTER_SEC,
        now=now,
    )

    connected_stale = should_reconnect_cctv(
        connection_status="CONNECTED",
        last_frame_at=(
            now
            - timedelta(seconds=25)
        ),
        stale_after_sec=STALE_AFTER_SEC,
        now=now,
    )

    disconnected_stale = should_reconnect_cctv(
        connection_status="DISCONNECTED",
        last_frame_at=(
            now
            - timedelta(seconds=25)
        ),
        stale_after_sec=STALE_AFTER_SEC,
        now=now,
    )

    reconnecting_stale = should_reconnect_cctv(
        connection_status="RECONNECTING",
        last_frame_at=(
            now
            - timedelta(seconds=25)
        ),
        stale_after_sec=STALE_AFTER_SEC,
        now=now,
    )

    print(
        f"CONNECTED + 5초 전  : "
        f"{connected_fresh}"
    )

    print(
        f"CONNECTED + 25초 전 : "
        f"{connected_stale}"
    )

    print(
        f"DISCONNECTED + 25초 : "
        f"{disconnected_stale}"
    )

    print(
        f"RECONNECTING + 25초 : "
        f"{reconnecting_stale}"
    )

    if connected_fresh:
        raise AssertionError(
            "정상 CONNECTED CCTV가 "
            "재연결 대상으로 판단되었습니다."
        )

    if not connected_stale:
        raise AssertionError(
            "Frame이 stale한 CONNECTED CCTV가 "
            "재연결 대상으로 판단되지 않았습니다."
        )

    if disconnected_stale:
        raise AssertionError(
            "DISCONNECTED CCTV를 "
            "Watchdog가 중복 재연결 대상으로 판단했습니다."
        )

    if reconnecting_stale:
        raise AssertionError(
            "이미 RECONNECTING인 CCTV를 "
            "중복 재연결 대상으로 판단했습니다."
        )


    # =====================================================
    # 결과
    # =====================================================

    print()
    print("=" * 70)
    print(
        "[SUCCESS] "
        "CCTV last_frame_at "
        "STALE 판정 정상"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()