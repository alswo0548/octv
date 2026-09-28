"""기관 조회·추천·선택 전달 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/agencies", tags=["기관 조회·추천·선택 전달"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("", summary="list_agencies · 구현 예정")
def list_agencies():
    return service.list_agencies()


@router.get(
    "/incidents/{incident_id}/recommendations",
    summary="list_recommendations · 구현 예정",
)
def list_recommendations(incident_id: int):
    return service.list_recommendations(incident_id)


@router.post("/incidents/{incident_id}/deliveries", summary="deliver · 구현 예정")
def deliver(incident_id: int, body: schemas.DeliveryRequest):
    return service.deliver(incident_id, body)
