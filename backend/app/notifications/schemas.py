"""사건 전달 알림 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from datetime import datetime


class NotificationResponse(BaseModel):
    id: int
    incident_id: int
    created_at: datetime
    read_at: datetime | None = None
    # DB 컬럼명 incidents_id를 API의 incident_id로 변환하세요.
