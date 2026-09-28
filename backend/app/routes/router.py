"""기관별 후보 경로 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/routes", tags=["기관별 후보 경로"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get(
    "/incidents/{incident_id}/agencies/{agency_id}",
    summary="list_candidates · 구현 예정",
)
def list_candidates(incident_id: int, agency_id: int):
    return service.list_candidates(incident_id, agency_id)
