from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from ..dependencies import require_control_admin
from . import schemas, service


router = APIRouter(
    prefix="/demo",
    tags=["Demo Scenario"],
)


@router.get(
    "/status",
    response_model=schemas.DemoStatusResponse,
    summary="Demo 상태 조회",
)
def get_demo_status(
    _admin=Depends(require_control_admin),
):
    return service.get_demo_status()


@router.get(
    "/scenarios/{scenario_name}",
    response_model=schemas.DemoScenarioResponse,
    summary="Demo Scenario 확인",
)
def get_demo_scenario(
    scenario_name: str,
    _admin=Depends(require_control_admin),
):
    try:
        return service.get_demo_scenario(scenario_name)

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except (
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/start",
    response_model=schemas.DemoStartResponse,
    summary="Demo 시작 사전검사",
)
def start_demo(
    body: schemas.DemoStartRequest,
    _admin=Depends(require_control_admin),
):
    """
    Demo 시작 전 필요한 설정과
    CCTV 존재 여부를 확인한다.

    현재 단계에서는 실제 Demo를
    시작하거나 DB 상태를 변경하지 않는다.
    """

    try:
        return service.start_demo(body.scenario)

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except service.DemoPreconditionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except (
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@router.post(
    "/stop",
    response_model=schemas.DemoStopResponse,
    summary="Demo 종료",
)
def stop_demo(
    body: schemas.DemoStopRequest,
    _admin=Depends(require_control_admin),
):
    try:
        return service.stop_demo(body.scenario)

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except service.DemoPreconditionError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except (
        FileNotFoundError,
        RuntimeError,
    ) as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
