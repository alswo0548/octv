"""통합관제 Dashboard API Schema."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    monitored_cctv_count: int = Field(ge=0)
    today_incident_count: int = Field(ge=0)
    connection_error_count: int = Field(ge=0)
    active_weather_alert_count: int = Field(ge=0)


class DashboardIncident(BaseModel):
    id: int
    incident_no: str
    hazard_type: str
    status: Literal["DETECTED", "CONFIRMED", "SENT"]
    priority: Literal["P1", "P2"]
    cctv_id: int
    cctv_name: str
    region_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    detected_at: datetime


class DashboardIncidentPage(BaseModel):
    items: list[DashboardIncident]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)



class DashboardResponse(BaseModel):
    summary: DashboardSummary
    incidents: DashboardIncidentPage


ExternalMetricStatus = Literal[
    "OK",
    "NO_MAPPING",
    "NO_DATA",
    "STALE",
    "TIMEOUT",
    "ERROR",
    "INVALID",
]


class DashboardExternalMetric(BaseModel):
    value: float | int | str | None = None
    unit: str
    observed_at: datetime | None = None
    status: ExternalMetricStatus


class DashboardWeatherAlert(BaseModel):
    external_alert_id: str
    alert_type: str
    alert_level: str
    title: str
    issued_at: datetime
    region_code: str


class DashboardOverviewExternalStatusResponse(
    BaseModel
):
    """
    W02에서 사건을 선택하지 않았을 때
    표시하는 전체 외부 상황.
    """
    last_received_at: datetime | None = None
    weather_alerts: list[DashboardWeatherAlert]
    # 도로통제 건수는 차단 차로 수와 다르므로 무조건 치환하지 않습니다.
    road_control_count: DashboardExternalMetric
    # 현재 ALERT 모드로 집중감시 중인 CCTV 수.
    focused_monitoring_cctv_count: int = Field(ge=0)


class DashboardExternalStatusResponse(BaseModel):
    """
    W02 외부 상황 패널.

    현재는 DB에서 확인 가능한
    기상특보 / 집중감시 CCTV 수를 실제 반환한다.

    기본 조회는 최근 LangGraph 저장 스냅샷만 반환한다.
    live=true 요청은 별도 MCP 읽기 전용 갱신을 시도하며 DB 분석값은 변경하지 않는다.
    """

    incident_id: int
    incident_no: str
    cctv_id: int
    cctv_name: str
    region_code: str | None = None
    region_name: str | None = None
    last_received_at: datetime | None = None
    weather_alerts: list[DashboardWeatherAlert]
    rainfall_mm: DashboardExternalMetric
    water_level_m: DashboardExternalMetric
    road_control_count: DashboardExternalMetric
    blocked_lane_count: DashboardExternalMetric | None = None
    # Latest MCP context versus historical LangGraph snapshot, not a DB update.
    external_data_source: str = "SAVED_SNAPSHOT"
    live_checked_at: datetime | None = None
    # ITS nearby alerts are location references, not verified control/closed lanes.
    nearby_traffic_event_count: int | None = Field(default=None, ge=0)
    mapping_state: dict[str, str] = Field(default_factory=dict)
    # Read-only example values for an explicitly assessed DEMO incident only.
    demo_mapping_preview: dict | None = None
    focused_monitoring_cctv_count: int = Field(ge=0)