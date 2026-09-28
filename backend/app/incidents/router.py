"""사건 조회·상세 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/incidents", tags=["사건 조회·상세"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("", summary="list_incidents · 구현 예정")
def list_incidents(page: int = 1, page_size: int = 5):
    return service.list_incidents(page, page_size)


@router.get("/{incident_id}", summary="get_incident · 구현 예정")
def get_incident(incident_id: int):
    return service.get_incident(incident_id)
