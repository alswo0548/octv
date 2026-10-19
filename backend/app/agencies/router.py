"""
기관 목록 API와
기관 추천 조회·선택 전달 API를 연결합니다.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
)

from ..dependencies import (
    get_current_user,
    require_control_admin,
)
from . import (
    schemas,
    service,
)


router = APIRouter(
    prefix="/agencies",
    tags=[
        "기관 조회·추천·선택 전달"
    ],
)


IncidentId = Annotated[
    int,
    Path(
        gt=0,
        le=9223372036854775807,
    ),
]


CurrentUser = Annotated[
    dict,
    Depends(
        get_current_user
    ),
]


AdminUser = Annotated[
    dict,
    Depends(
        require_control_admin
    ),
]


# ------------------------------------------------------------
# 회원가입용 기관 목록
# ------------------------------------------------------------

@router.get(
    "",
    response_model=list[
        schemas.AgencyResponse
    ],
    summary=(
        "회원가입용 기관 목록 조회"
    ),
)
def list_agencies():
    """
    회원가입 화면에서 사용하므로
    인증 없이 조회 가능하다.
    """

    return service.list_agencies()


# ------------------------------------------------------------
# 추천 기관 / 경로 조회
# ------------------------------------------------------------

@router.get(
    "/incidents/{incident_id}/recommendations",
    response_model=(
        schemas.DeliveryCandidatesResponse
    ),
    summary=(
        "기관 추천·경로 후보 조회"
    ),
)
def list_recommendations(
    incident_id: IncidentId,
    user: CurrentUser,
):
    """
    CONTROL_ADMIN
    → 사건의 모든 추천 기관과 경로 조회

    AGENCY_STAFF / RESPONDER
    → 자기 소속 기관에 전달된 경우에만
      자기 기관의 추천정보와 경로 조회
    """

    return service.list_recommendations(
        incident_id,
        user,
    )


# ------------------------------------------------------------
# 기관 전달
# ------------------------------------------------------------

@router.post(
    "/incidents/{incident_id}/deliveries",
    response_model=(
        schemas.DeliveryResponse
    ),
    summary=(
        "선택 기관에 사건 전달 및 DB 알림 생성"
    ),
)
def deliver(
    incident_id: IncidentId,
    body: schemas.DeliveryRequest,
    user: AdminUser,
):
    """
    기관 전달은 관제 관리자만 수행할 수 있다.
    """

    return service.deliver(
        incident_id,
        body,
        user,
    )


# ------------------------------------------------------------
# 현장 대응 완료
# ------------------------------------------------------------

@router.patch(
    "/incidents/{incident_id}/complete",
    response_model=(
        schemas.DeliveryCompletionResponse
    ),
    summary=(
        "현장 대응 완료 처리"
    ),
)
def complete_delivery(
    incident_id: IncidentId,
    user: CurrentUser,
):
    """
    현장대응자가 자신의 소속 기관에 전달된
    사건의 대응 완료를 처리합니다.

    마지막 대응 기관까지 완료되면
    Incident도 RESOLVED로 변경됩니다.
    """

    return service.complete_delivery(
        incident_id,
        user,
    )