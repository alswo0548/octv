"""CCTV 조회·감시 상태 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from typing import Literal


class CctvResponse(BaseModel):
    id: int
    name: str
    connection_status: Literal["CONNECTED", "DISCONNECTED", "RECONNECTING"]
    is_monitored: bool
    monitored_mode: Literal["BASE", "ALERT", "POST_ALERT", "VERIFY"] | None
    # OFF는 is_monitored=False. UI 표시 문구와 DB 값을 구분합니다.


class MonitoringRequest(BaseModel):
    enabled: bool
    # TODO: 관리자 확인 절차·감사 기록 계약을 합의하세요.
