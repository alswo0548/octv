"""
기관 목록을 조회하며, 기관 추천 및 전달을 담당

주요 기능
- WEB과 백엔드 사이에서 주고받는 데이터의 형식을 정의하고 검사 (기관 ID가 올바른지, 같은 기관을 중복 선택했는지 등)
"""

from typing import Annotated, Any, Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator


# 회원가입에 사용할 기관 정보의 응답 형식
class AgencyResponse(BaseModel):
    id: int
    name: str
    agency_type: str


# PostgreSQL BIGINT 범위의 양수 정수만 ID로 받으며 문자·소수·불리언은 자동 변환하지 않습니다.
DatabaseId = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]


# 기관을 선택하고, 같은 기관을 중복 선택하지 못하도록 검사
class DeliverySelection(BaseModel):
    # user_id나 role 등 요청 계약에 없는 임의의 필드는 조용히 무시하지 않고 거부합니다.
    model_config = ConfigDict(extra="forbid")

    agency_id: DatabaseId
    route_candidate_id: DatabaseId | None = None


# 여러 기관 선택 및 중복 검사
class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # 기관 여러개의 선택 정보를 담은 리스트중 최소 1곳 이상 선택해야함.
    selections: list[DeliverySelection] = Field(min_length=1)

    # 각 기관 ID 검증이 끝난 후, set으로 중복을 제거했을 때 개수가 달라지는지 확인합니다.
    @model_validator(mode="after")
    def validate_unique_agencies(self) -> Self:
        agency_ids = [selection.agency_id for selection in self.selections]
        # 여기서 같은 기관이 두번 선택되었는지 확인.
        if len(agency_ids) != len(set(agency_ids)):
            raise ValueError("같은 기관은 한 번만 선택해 주세요.")
        return self


# 경로 후보 정보
class DeliveryRoute(BaseModel):
    id: int
    route_name: str
    distance_m: int
    duration_sec: int
    total_score: float | None = None
    score_breakdown_json: dict[str, Any] | None = None
    disqualify_reason: str | None = None
    route_path_json: dict[str, Any]
    rule_version: str


# 추천 기관 정보
class DeliveryCandidate(BaseModel):
    agency_recommendation_id: int
    agency_id: int
    agency_name: str
    agency_type: str
    recommendation_rank: int
    recommendation_score: float
    recommendation_status: Literal["RECOMMENDED", "DELIVERED", "COMPLETED"]
    score_breakdown_json: dict[str, Any]
    rule_version: str
    routes: list[DeliveryRoute] = Field(default_factory=list)


# 추천 조회 전체 결과
class DeliveryCandidatesResponse(BaseModel):
    incident_id: int
    incident_status: str
    items: list[DeliveryCandidate]


# 기관별 전달 결과
class DeliveryItem(BaseModel):
    agency_id: int
    agency_recommendation_id: int
    status: Literal["DELIVERED", "COMPLETED"]
    newly_delivered: bool
    created_notification_count: int = Field(ge=0)


# 최종 전달 결과
class DeliveryResponse(BaseModel):
    incident_id: int
    incident_status: Literal["CONFIRMED", "SENT"]
    items: list[DeliveryItem]
    created_notification_count: int = Field(ge=0)
    # 큐 등록 결과이지 FCM 접수나 휴대폰 표시 성공 여부가 아닙니다.
    push_status: Literal[
        "NOT_QUEUED", "QUEUED", "PARTIALLY_QUEUED", "QUEUE_UNCONFIRMED",
        "DISABLED", "NO_NEW_NOTIFICATIONS",
    ] = "NOT_QUEUED"


# 현장 대응 완료 결과
class DeliveryCompletionResponse(BaseModel):
    incident_id: int
    agency_id: int
    agency_recommendation_id: int
    recommendation_status: Literal["COMPLETED"]
    incident_status: Literal["SENT", "RESOLVED"]