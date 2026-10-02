"""사건 조회·상세 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from typing import Literal
from datetime import datetime
from decimal import Decimal


class IncidentResponse(BaseModel):
    id: int
    incident_no: str
    cctv_id: int
    hazard_type: str
    status: Literal["DETECTED", "CONFIRMED", "SENT", "RESOLVED", "FALSE_POSITIVE"]
    confidence: Decimal
    detected_at: datetime
    # TODO: 상세에서 상황 스냅샷·평가·최근 지원요청을 조합하세요.
