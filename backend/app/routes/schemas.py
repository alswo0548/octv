"""기관별 후보 경로 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel
from decimal import Decimal


class RouteCandidateResponse(BaseModel):
    id: int
    route_name: str
    distance_m: int
    duration_sec: int
    total_score: Decimal | None = None
    disqualify_reason: str | None = None
    # TODO: route_path_json 좌표 구조와 점수 세부 계약을 합의하세요.
