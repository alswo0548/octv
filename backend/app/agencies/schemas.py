"""기관 조회·추천·선택 전달 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel


class AgencyResponse(BaseModel):
    id: int
    name: str
    agency_type: str


class DeliverySelection(BaseModel):
    agency_id: int
    route_candidate_id: int


class DeliveryRequest(BaseModel):
    selections: list[DeliverySelection]
    # TODO: 1개 이상·중복 기관·사건/기관/경로의 일치 여부를 검증하세요.
