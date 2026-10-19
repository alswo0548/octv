"""사건 통계 필터와 집계 응답. 날짜는 한국시간, 신뢰도는 저장된 탐지 점수입니다."""

from pydantic import BaseModel, Field, model_validator
from datetime import date, datetime, timedelta, timezone


def seoul_today():
    return datetime.now(timezone(timedelta(hours=9))).date()


class StatsFilters(BaseModel):
    start: date = Field(default_factory=lambda: seoul_today() - timedelta(days=29))
    end: date = Field(default_factory=seoul_today)
    region_code: str | None = Field(default=None, min_length=1, max_length=100)
    cctv_id: int | None = Field(default=None, gt=0, le=9223372036854775807)
    confirmed_only: bool = True

    @model_validator(mode="after")
    def validate_period(self):
        if self.start <= date.min or self.end >= date.max or self.end < self.start or (self.end - self.start).days > 365:
            raise ValueError("시작일~종료일은 순서대로 최대 366일이어야 합니다.")
        return self


class DailyIncidentCount(BaseModel):
    day: date
    count: int


class HourlyIncidentCount(BaseModel):
    hour: int
    count: int


class StatsResponse(BaseModel):
    confirmed_incident_count: int
    daily: list[DailyIncidentCount]
    # 모든 분포와 추이는 같은 필터를 사용합니다. 기관별 JOIN은 하지 않습니다.
    filters: StatsFilters
    timezone: str = "Asia/Seoul"
    total_incident_count: int
    by_status: dict[str, int]
    by_hazard: dict[str, int]
    by_risk: dict[str, int]
    by_priority: dict[str, int]
    confidence_distribution: dict[str, int]
    average_confidence: float | None
    hourly: list[HourlyIncidentCount]
