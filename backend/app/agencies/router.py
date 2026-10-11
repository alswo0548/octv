"""기관 조회·추천·전달 요청을 Service로 연결합니다."""

from fastapi import APIRouter

from . import schemas, service

router = APIRouter(prefix="/agencies", tags=["기관 조회·추천·선택 전달"])


@router.get(
    "",
    response_model=list[schemas.AgencyResponse],
    summary="회원가입용 기관 목록 조회",
)
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
