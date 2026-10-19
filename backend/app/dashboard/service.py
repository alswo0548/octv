"""통합관제 Dashboard Service."""

from datetime import (
    datetime,
    time,
    timedelta,
    timezone,
)
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas


KST = ZoneInfo(
    "Asia/Seoul"
)


class DashboardIncidentNotFoundError(
    LookupError
):
    """Dashboard 외부상황 기준 사건을 찾지 못한 경우."""


def _today_utc_range() -> tuple[
    datetime,
    datetime,
]:
    """한국시간 오늘 범위를 UTC naive로 변환한다."""

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
    """DB의 UTC naive timestamp를 KST로 변환한다."""

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        KST
    )


def _kst_naive_to_aware(
    value: datetime,
) -> datetime:
    """weather_alerts KST naive timestamp를 aware KST로 변환한다."""

    if value.tzinfo is None:
        return value.replace(
            tzinfo=KST
        )

    return value.astimezone(
        KST
    )


def _unmapped_metric(
    unit: str,
) -> schemas.DashboardExternalMetric:
    """외부 API/MCP 연결 전 기본 응답."""

    return schemas.DashboardExternalMetric(
        value=None,
        unit=unit,
        observed_at=None,
        status="NO_MAPPING",
    )


def _role_scope(
    user: dict,
) -> tuple[bool, int | None]:
    """
    Dashboard 조회 범위를 결정한다.

    CONTROL_ADMIN:
        전체 조회

    AGENCY_STAFF / RESPONDER:
        자신의 agency_id에 전달된 사건만 조회
    """

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    if user["role"] == "CONTROL_ADMIN":
        return (
            False,
            None,
        )

    return (
        True,
        user.get(
            "agency_id"
        ),
    )


def get_dashboard(
    page: int = 1,
    page_size: int = 5,
    user: dict | None = None,
) -> schemas.DashboardResponse:
    """
    W02 통합관제 화면 데이터를 반환한다.

    - CONTROL_ADMIN: 전체 현황
    - AGENCY_STAFF / RESPONDER:
      소속 기관에 전달된 사건 범위
    - 사건 목록과 지도는 동일한 incidents.items 사용
    - 오늘 등록 사건은 한국 날짜 기준
    - 사건 탐지 시각은 KST(+09:00)로 반환
    """

    agency_scoped, agency_id = (
        _role_scope(
            user
        )
    )

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
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        total = (
            repository.count_dashboard_incidents(
                connection,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        incidents = (
            repository.list_dashboard_incidents(
                connection,
                page=page,
                page_size=page_size,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
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


def get_external_status(
    incident_id: int,
    user: dict | None = None,
) -> schemas.DashboardExternalStatusResponse:
    """
    선택한 사건 기준 W02 외부 상황 정보를 반환한다.

    CONTROL_ADMIN:
    - 전체 사건 접근 가능

    AGENCY_STAFF / RESPONDER:
    - 자기 기관에 DELIVERED / COMPLETED된 사건만 접근 가능

    현재:
    - 기상특보 실제 조회
    - 집중감시 CCTV 수 실제 조회
    - 강수량 / 수위 / 도로통제는 NO_MAPPING
    """

    agency_scoped, agency_id = (
        _role_scope(
            user
        )
    )

    with get_connection() as connection:
        incident = (
            repository.get_external_status_incident(
                connection,
                incident_id,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        if incident is None:
            raise (
                DashboardIncidentNotFoundError(
                    f"incident_id={incident_id}"
                )
            )

        weather_rows = (
            repository.list_active_weather_alerts(
                connection,
                incident[
                    "region_code"
                ],
            )
        )

        focused_count = (
            repository.count_focused_monitoring_cctvs(
                connection,
                incident[
                    "region_code"
                ],
            )
        )

    weather_alerts = [
        schemas.DashboardWeatherAlert(
            external_alert_id=(
                row[
                    "external_alert_id"
                ]
            ),
            alert_type=(
                row[
                    "alert_type"
                ]
            ),
            alert_level=(
                row[
                    "alert_level"
                ]
            ),
            title=(
                row[
                    "title"
                ]
            ),
            issued_at=(
                _kst_naive_to_aware(
                    row[
                        "issued_at"
                    ]
                )
            ),
            region_code=(
                row[
                    "region_code"
                ]
            ),
        )

        for row in weather_rows
    ]

    return (
        schemas.DashboardExternalStatusResponse(
            incident_id=(
                incident[
                    "id"
                ]
            ),
            incident_no=(
                incident[
                    "incident_no"
                ]
            ),
            cctv_id=(
                incident[
                    "cctv_id"
                ]
            ),
            cctv_name=(
                incident[
                    "cctv_name"
                ]
            ),
            region_code=(
                incident[
                    "region_code"
                ]
            ),
            region_name=(
                incident[
                    "region_name"
                ]
            ),
            last_received_at=None,
            weather_alerts=(
                weather_alerts
            ),
            rainfall_mm=(
                _unmapped_metric(
                    "mm"
                )
            ),
            water_level_m=(
                _unmapped_metric(
                    "m"
                )
            ),
            road_control_count=(
                _unmapped_metric(
                    "count"
                )
            ),
            focused_monitoring_cctv_count=(
                focused_count
            ),
        )
    )