"""통합관제 Dashboard Service."""

from datetime import (
    datetime,
    time,
    timedelta,
    timezone,
)
from zoneinfo import ZoneInfo

from ..db.session import get_connection
from . import repository, schemas


KST = ZoneInfo(
    "Asia/Seoul"
)


def _today_utc_range() -> tuple[
    datetime,
    datetime,
]:
    """
    한국시간 기준 오늘의 시작과 끝을 구한 뒤
    incidents DB 저장 기준인 UTC naive 값으로 변환한다.

    예:
        2026-10-19 00:00:00+09:00
        ->
        2026-10-18 15:00:00
    """

    today_kst = datetime.now(
        KST
    ).date()

    start_kst = datetime.combine(
        today_kst,
        time.min,
        tzinfo=KST,
    )

    end_kst = (
        start_kst
        + timedelta(
            days=1
        )
    )

    start_utc = (
        start_kst
        .astimezone(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
    )

    end_utc = (
        end_kst
        .astimezone(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
    )

    return (
        start_utc,
        end_utc,
    )


def _utc_naive_to_kst(
    value: datetime,
) -> datetime:
    """
    DB의 UTC naive timestamp를
    timezone-aware 한국시간으로 변환한다.
    """

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        KST
    )


def get_dashboard(
    page: int = 1,
    page_size: int = 5,
) -> schemas.DashboardResponse:
    """
    W02 통합관제 화면 데이터를 반환한다.

    - 사건 목록과 지도는 동일한 incidents.items 사용
    - 오늘 등록 사건은 한국 날짜 기준
    - 사건 탐지 시각은 API에서 한국시간(+09:00)으로 반환
    """

    (
        today_start_utc,
        today_end_utc,
    ) = _today_utc_range()

    with get_connection() as connection:
        summary = (
            repository.get_dashboard_summary(
                connection,
                today_start_utc=(
                    today_start_utc
                ),
                today_end_utc=(
                    today_end_utc
                ),
            )
        )

        total = (
            repository.count_dashboard_incidents(
                connection
            )
        )

        incidents = (
            repository.list_dashboard_incidents(
                connection,
                page=page,
                page_size=page_size,
            )
        )

    total_pages = (
        (
            total
            + page_size
            - 1
        )
        // page_size
        if total > 0
        else 0
    )

    incident_items = []

    for incident in incidents:
        incident_data = {
            **incident,
            "detected_at":
                _utc_naive_to_kst(
                    incident[
                        "detected_at"
                    ]
                ),
        }

        incident_items.append(
            schemas.DashboardIncident(
                **incident_data
            )
        )

    return schemas.DashboardResponse(
        summary=(
            schemas.DashboardSummary(
                **summary
            )
        ),

        incidents=(
            schemas.DashboardIncidentPage(
                items=incident_items,

                total=total,

                page=page,

                page_size=page_size,

                total_pages=(
                    total_pages
                ),
            )
        ),
    )