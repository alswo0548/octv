"""
추가 지원요청을 받을 때 입력값을 검사하고, DB 저장 결과를 어떤 형식으로 반환할지 정의하는 파일

기존 테이블과 ENUM을 그대로 사용하고, 요청 작성자·기관은 JWT로 결정.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# 현장 대원이 모바일에서 전송하는 지원요청 데이터를 검사
class SupportRequestCreate(BaseModel):
    # 정의되지 않은 필드를 사용자가 추가하면 거부
    model_config = ConfigDict(extra="forbid")

    support_type: Literal["PERSONNEL", "EQUIPMENT", "TRAFFIC_CONTROL", "OTHER"]
    request_content: str = Field(min_length=1, max_length=2000)

    @field_validator("request_content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        # 공백만 입력하거나 공백으로 글자 수를 채운 요청은 저장하지 않습니다.
        text = value.strip()
        if not text:
            raise ValueError("요청 내용을 입력해 주세요.")
        return text


class SupportRequestResponse(SupportRequestCreate):
    id: int
    incident_id: int
    responder_id: int
    agency_id: int
    created_at: datetime
    responder_name: str | None = None
    agency_name: str | None = None
