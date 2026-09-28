"""추가 지원요청 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/support-requests", tags=["추가 지원요청"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("/incidents/{incident_id}", summary="list_support_requests · 구현 예정")
def list_support_requests(incident_id: int):
    return service.list_support_requests(incident_id)


@router.post("/incidents/{incident_id}", summary="create_support_request · 구현 예정")
def create_support_request(incident_id: int, body: schemas.SupportRequestCreate):
    return service.create_support_request(incident_id, body)
