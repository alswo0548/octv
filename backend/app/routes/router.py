"""기관별 저장 경로 HTTP API. 기존 JWT로 인증하고 Service에서 소속·전달 여부를 확인.

흐름: GET /api/routes/incidents/{id}/agencies/{id} → 인증 사용자 → 경로 Service → DB 조회.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ..dependencies import get_current_user
from . import schemas, service

router = APIRouter(prefix="/routes", tags=["기관별 후보 경로"])
DatabaseId = Annotated[int, Path(gt=0, le=9223372036854775807)]
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get(
    "/incidents/{incident_id}/agencies/{agency_id}",
    response_model=schemas.RouteCandidatesResponse,
    summary="기관별 저장 경로와 확인 상태 조회",
)
def list_candidates(incident_id: DatabaseId, agency_id: DatabaseId, user: CurrentUser):
    return service.list_candidates(incident_id, agency_id, user)
