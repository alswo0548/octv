"""통합관제 Dashboard 응답 Schema."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    monitored_cctv_count: int = Field(
        ge=0
    )

    today_incident_count: int = Field(
        ge=0
    )

    connection_error_count: int = Field(
        ge=0
    )

    active_weather_alert_count: int = Field(
        ge=0
    )


class DashboardIncident(BaseModel):
    id: int

    incident_no: str

    hazard_type: str

    status: Literal[
        "DETECTED",
        "CONFIRMED",
        "SENT",
    ]

    priority: Literal[
        "P1",
        "P2",
    ]

    cctv_id: int

    cctv_name: str

    region_name: str | None = None

    latitude: float | None = None

    longitude: float | None = None

    detected_at: datetime


class DashboardIncidentPage(BaseModel):
    items: list[
        DashboardIncident
    ]

    total: int = Field(
        ge=0
    )

    page: int = Field(
        ge=1
    )

    page_size: int = Field(
        ge=1
    )

    total_pages: int = Field(
        ge=0
    )


class DashboardResponse(BaseModel):
    summary: DashboardSummary

    incidents: DashboardIncidentPage