"""추가 지원요청 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from typing import Literal
from datetime import datetime


class SupportRequestCreate(BaseModel):
    support_type: Literal["PERSONNEL", "EQUIPMENT", "TRAFFIC_CONTROL", "OTHER"]
    request_content: str


class SupportRequestResponse(SupportRequestCreate):
    id: int
    incident_id: int
    responder_id: int
    agency_id: int
    created_at: datetime
