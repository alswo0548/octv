"""운영 통계 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from datetime import date


class DailyIncidentCount(BaseModel):
    day: date
    count: int


class StatsResponse(BaseModel):
    confirmed_incident_count: int
    daily: list[DailyIncidentCount]
    # TODO: 현재 통계 화면에 필요한 나머지 집계 필드를 합의하세요.
