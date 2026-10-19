"""통합관제 Dashboard API Router."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from ..dependencies import (
    require_control_admin,
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

    _admin=Depends(
        require_control_admin
    ),
):
    """
    W02 통합관제 메인 데이터를 조회한다.

    같은 incidents.items 배열을
    긴급 사건 목록과 지도 마커에 함께 사용한다.
    """

    return service.get_dashboard(
        page=page,
        page_size=page_size,
    )


@router.get(
    "/incidents/{incident_id}/external-status",
    response_model=(
        schemas.DashboardExternalStatusResponse
    ),
)
def get_dashboard_external_status(
    incident_id: int,
    _admin=Depends(
        require_control_admin
    ),
):
    """
    W02에서 선택한 사건의 외부 상황을 조회한다.

    현재:
    - 기상특보
    - 집중감시 CCTV 수

    추후 MCP 연결:
    - 강수량
    - 수위
    - 도로통제
    - 마지막 수신시각
    """

    try:
        return (
            service.get_external_status(
                incident_id
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