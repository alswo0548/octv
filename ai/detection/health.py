"""CCTV Frame 수신 상태를 판단하는 Health Check 로직."""

from datetime import datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def calculate_frame_age_sec(
    last_frame_at: datetime | None,
    now: datetime | None = None,
) -> float | None:
    """
    마지막 Frame 수신 후 몇 초가 지났는지 계산한다.

    DB의 last_frame_at은
    TIMESTAMP WITHOUT TIME ZONE이고
    현재 OCTV에서는 KST 시각을 저장하고 있으므로
    조회한 값에 KST timezone을 다시 붙여 계산한다.

    last_frame_at이 없으면 None을 반환한다.
    """

    if last_frame_at is None:
        return None

    if last_frame_at.tzinfo is None:
        last_frame_at = (
            last_frame_at.replace(
                tzinfo=KST
            )
        )

    if now is None:
        now = datetime.now(KST)

    elif now.tzinfo is None:
        now = now.replace(
            tzinfo=KST
        )

    age_sec = (
        now
        - last_frame_at
    ).total_seconds()

    # 시스템 시간 보정 등으로
    # 음수가 나오는 경우 0초로 처리
    return max(
        0.0,
        age_sec,
    )


def is_frame_stale(
    last_frame_at: datetime | None,
    stale_after_sec: float = 20.0,
    now: datetime | None = None,
) -> bool:
    """
    마지막 Frame이 너무 오래 갱신되지 않았는지 판단한다.

    True:
        last_frame_at 이후 stale_after_sec 초과

    False:
        최근 Frame이 정상적으로 들어옴

    last_frame_at=None은 아직 판단할 기준 Frame이 없으므로
    여기서는 False로 처리한다.

    최초 Frame 자체가 오지 않는 문제는
    CaptureWorker의 연결/수신 실패 로직에서 처리한다.
    """

    if stale_after_sec <= 0:
        raise ValueError(
            "stale_after_sec은 0보다 커야 합니다."
        )

    age_sec = calculate_frame_age_sec(
        last_frame_at=last_frame_at,
        now=now,
    )

    if age_sec is None:
        return False

    return (
        age_sec
        > stale_after_sec
    )


def should_reconnect_cctv(
    connection_status: str,
    last_frame_at: datetime | None,
    stale_after_sec: float = 20.0,
    now: datetime | None = None,
) -> bool:
    """
    CCTV를 재연결해야 하는 상태인지 판단한다.

    조건:
    1. DB상 현재 CONNECTED 상태이고
    2. 마지막 Frame이 stale 기준을 초과했을 때만 True

    DISCONNECTED / RECONNECTING 상태는
    별도 재연결 로직이 이미 담당하므로
    여기서는 다시 재연결 대상으로 판단하지 않는다.
    """

    if connection_status != "CONNECTED":
        return False

    return is_frame_stale(
        last_frame_at=last_frame_at,
        stale_after_sec=stale_after_sec,
        now=now,
    )