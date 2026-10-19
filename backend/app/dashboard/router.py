"""통합관제 Dashboard API Router."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from ..dependencies import (
    get_current_user,
)
from . import schemas, service


router = APIRouter(
    prefix="/dashboard",
    tags=[
        "dashboard",
    ],
)


@router.get(
    "",
    response_model=(
        schemas.DashboardResponse
    ),
)
def get_dashboard(
    page: int = Query(
        default=1,
        ge=1,
    ),
    page_size: int = Query(
        default=5,
        ge=1,
        le=20,
    ),
    user=Depends(
        get_current_user
    ),
):
    """
    W02 통합관제 메인 데이터를 조회한다.

    CONTROL_ADMIN:
    - 전체 현황과 전체 P1/P2 사건

    AGENCY_STAFF / RESPONDER:
    - 소속 기관에 전달된 사건 범위만 조회

    같은 incidents.items 배열을
    긴급 사건 목록과 지도 마커에 함께 사용한다.
    """

    return service.get_dashboard(
        page=page,
        page_size=page_size,
        user=user,
    )


@router.get(
    "/incidents/{incident_id}/external-status",
    response_model=(
        schemas.DashboardExternalStatusResponse
    ),
)
def get_dashboard_external_status(
    incident_id: int,
    user=Depends(
        get_current_user
    ),
):
    """
    W02에서 선택한 사건의 외부 상황을 조회한다.

    기관/현장 사용자는 소속 기관에 전달된 사건만
    조회할 수 있으며, 접근 불가 사건은 404로 숨긴다.
    """

    try:
        return (
            service.get_external_status(
                incident_id,
                user=user,
            )
        )

    except (
        service.DashboardIncidentNotFoundError
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=(
                "사건을 찾을 수 없습니다."
            ),
        ) from None