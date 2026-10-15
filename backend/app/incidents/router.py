"""사건 목록·상세·상태 변경 요청을 검증하고 Service 결과를 반환합니다."""

from datetime import datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
)

from . import schemas, service
from ..dependencies import (
    get_current_user,
    require_control_admin,
)
from ..analysis_requests import (
    request_analysis,
)


router = APIRouter(
    prefix="/incidents",
    tags=["사건 조회·상세"],
)


@router.get(
    "",
    response_model=schemas.IncidentPage,
    summary="사건 목록 조회",
)
def list_incidents(
    page: int = Query(
        1,
        ge=1,
    ),
    page_size: int = Query(
        5,
        ge=1,
        le=100,
    ),
    status: Literal[
        "DETECTED",
        "CONFIRMED",
        "SENT",
        "RESOLVED",
        "FALSE_POSITIVE",
    ]
    | None = None,
    hazard_type: str | None = None,
    priority: Literal[
        "P1",
        "P2",
        "P3",
    ]
    | None = None,
    region_code: str | None = None,
    cctv_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    q: str | None = None,
    confirmed_only: bool = False,
    active_only: bool = False,
    user=Depends(
        get_current_user
    ),
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

    # DB와 같은 UTC 기준으로 맞춥니다.
    # 시간대 없는 입력은 422로 반환합니다.
    for key, value in (
        (
            "start",
            start,
        ),
        (
            "end",
            end,
        ),
    ):
        if value is not None:
            try:
                filters[key] = (
                    service.utc_naive(
                        value
                    )
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(
                        exc
                    ),
                ) from exc

    return service.list_incidents(
        page,
        page_size,
        filters,
        user,
    )


# ------------------------------------------------------------
# 사용자가 사건을 클릭해 확인
# DETECTED → CONFIRMED
# ------------------------------------------------------------
@router.patch(
    "/{incident_id}/confirm",
    response_model=schemas.IncidentResponse,
    summary="사건 확인 처리",
)
def confirm_incident(
    incident_id: int,
    user=Depends(
        require_control_admin
    ),
):
    return service.confirm_incident(
        incident_id,
        user,
    )


# ------------------------------------------------------------
# 관리자 오탐 처리
# DETECTED / CONFIRMED → FALSE_POSITIVE
# ------------------------------------------------------------
@router.patch(
    "/{incident_id}/false-positive",
    response_model=schemas.IncidentResponse,
    summary="사건 오탐 처리",
)
def mark_false_positive(
    incident_id: int,
    user=Depends(
        require_control_admin
    ),
):
    return service.mark_false_positive(
        incident_id,
        user,
    )


# ------------------------------------------------------------
# 실제 기관 전달 성공 후 상태 기록
# CONFIRMED → SENT
#
# 이 API가 기관 전달 자체를 수행하는 것은 아닙니다.
# ------------------------------------------------------------
@router.patch(
    "/{incident_id}/sent",
    response_model=schemas.IncidentResponse,
    summary="사건 전달 완료 처리",
)
def mark_sent(
    incident_id: int,
    user=Depends(
        require_control_admin
    ),
):
    return service.mark_sent(
        incident_id,
        user,
    )


# 관리자가 특정 사건의 AI 판단을
# 수동으로 다시 요청하는 보조 기능입니다.
@router.post(
    "/{incident_id}/analysis",
    status_code=202,
    summary="사건 AI 분석 요청",
)
def request_incident_analysis(
    incident_id: int,
    user=Depends(
        require_control_admin
    ),
):
    return request_analysis(
        incident_id
    )


@router.get(
    "/{incident_id}/image",
    summary="사건 대표 이미지 조회",
    response_class=Response,
)
def get_incident_image(
    incident_id: int,
    user=Depends(
        get_current_user
    ),
):
    image_bytes = (
        service.get_incident_image(
            incident_id,
            user,
        )
    )

    return Response(
        content=image_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control":
                "no-store",
        },
    )


@router.get(
    "/{incident_id}",
    response_model=schemas.IncidentResponse,
    summary="사건 상세 조회",
)
def get_incident(
    incident_id: int,
    user=Depends(
        get_current_user
    ),
):
    return service.get_incident(
        incident_id,
        user,
    )