
"""사건 목록·상세 요청을 검증하고 Service 결과를 응답 모델로 반환합니다."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Literal

from . import schemas, service
from ..dependencies import get_current_user, require_control_admin
from ..analysis_requests import request_analysis

router = APIRouter(prefix="/incidents", tags=["사건 조회·상세"])


@router.get("", response_model=schemas.IncidentPage, summary="사건 목록 조회")
def list_incidents(
    page: int = Query(1, ge=1),
    page_size: int = Query(5, ge=1, le=100),
    status: Literal[
        "DETECTED", "CONFIRMED", "SENT", "RESOLVED", "FALSE_POSITIVE"
    ] | None = None,
    hazard_type: str | None = None,
    priority: Literal["P1", "P2", "P3"] | None = None,
    region_code: str | None = None,
    cctv_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    q: str | None = None,
    confirmed_only: bool = False,
    active_only: bool = False,
    user=Depends(get_current_user),
):
    filters = dict(
        status=status,
        hazard_type=hazard_type,
        priority=priority,
        region_code=region_code,
        cctv_id=cctv_id,
        q=q,
        confirmed_only=confirmed_only,
        active_only=active_only,
    )

    # DB와 같은 UTC 기준으로 맞추고, 시간대가 없는 입력은 422로 반환합니다.
    for key, value in (("start", start), ("end", end)):
        if value is not None:
            try:
                filters[key] = service.utc_naive(value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc)
                ) from exc
    # 기관 범위를 Service에서 결정하도록 인증된 사용자를 함께 전달합니다.
    return service.list_incidents(page, page_size, filters, user)

@router.get(
    "/{incident_id}",
    response_model=schemas.IncidentResponse,
    summary="사건 상세 조회",
)
def get_incident(
    incident_id: int,
    user=Depends(get_current_user)
):
    return service.get_incident(incident_id, user)

# 관리자가 특정 사건의 AI 판단을 수동으로 요청하는 API.
# 자동 판단 실패 시 재요청하거나 개발 중 테스트하는 보조 기능.
@router.post(
    "/{incident_id}/analysis",
    status_code=202
)
def request_incident_analysis(
    incident_id: int,
    user=Depends(require_control_admin)
):
    return request_analysis(incident_id)
