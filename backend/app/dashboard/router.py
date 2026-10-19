"""통합관제 Dashboard HTTP API."""

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from ..dependencies import (
    require_control_admin,
)
from . import (
    schemas,
    service,
)


router = APIRouter(
    prefix="/dashboard",
    tags=[
        "통합관제"
    ],
)


@router.get(
    "",
    response_model=(
        schemas.DashboardResponse
    ),
    summary="통합관제 Dashboard 조회",
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
    _current_user=Depends(
        require_control_admin
    ),
):
    return service.get_dashboard(
        page=page,
        page_size=page_size,
    )