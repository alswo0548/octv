"""관리자 통계 API: JWT·역할 확인→날짜/지역/CCTV 필터 검증→집계 조회."""

from typing import Annotated
from fastapi import APIRouter, Depends, Query
from ..dependencies import require_control_admin
from . import schemas, service

router = APIRouter(prefix="/stats", tags=["운영 통계"])
# 기존 관리자 권한을 재사용하며 기관 사용자에게 전체 통계를 노출하지 않습니다.


@router.get("", response_model=schemas.StatsResponse, summary="실제 사건 운영통계")
def get_stats(filters: Annotated[schemas.StatsFilters, Query()], _admin=Depends(require_control_admin)):
    return service.get_stats(filters)
