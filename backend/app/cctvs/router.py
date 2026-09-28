"""CCTV 조회·감시 상태 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/cctvs", tags=["CCTV 조회·감시 상태"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("", summary="list_cctvs · 구현 예정")
def list_cctvs():
    return service.list_cctvs()


@router.get("/{cctv_id}", summary="get_cctv · 구현 예정")
def get_cctv(cctv_id: int):
    return service.get_cctv(cctv_id)


@router.patch("/{cctv_id}/monitoring", summary="change_monitoring · 구현 예정")
def change_monitoring(cctv_id: int, body: schemas.MonitoringRequest):
    return service.change_monitoring(cctv_id, body)
