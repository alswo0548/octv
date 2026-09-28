"""운영 통계 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/stats", tags=["운영 통계"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.get("", summary="get_stats · 구현 예정")
def get_stats():
    return service.get_stats()
