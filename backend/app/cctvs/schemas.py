"""CCTV 조회·감시 상태 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from typing import Literal


class CctvResponse(BaseModel):
    id: int
    name: str
    connection_status: Literal["CONNECTED", "DISCONNECTED", "RECONNECTING"]
    is_monitored: bool
    monitored_mode: Literal["BASE", "ALERT", "VERIFY", "POST_ALERT", "OFF"] | None
    # ERD: is_monitored는 기본 감시 대상 여부, monitored_mode는 현재 감시 상태입니다.


class MonitoringRequest(BaseModel):
    enabled: bool
    # TODO: 관리자 확인 절차·감사 기록 계약을 합의하세요.
