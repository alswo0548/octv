from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from fastapi.responses import FileResponse

from ..dependencies import (
    get_current_user,
    require_control_admin,
)
from . import schemas, service


router = APIRouter(
    prefix="/demo",
    tags=["Demo Scenario"],
)


@router.get(
    "/cctvs/{cctv_id}/video",
    response_class=FileResponse,
    summary="Demo CCTV 영상 재생",
)
def get_demo_cctv_video(
    cctv_id: int,
    _user=Depends(get_current_user),
    mobile_compatible: bool = Query(False),
):
    """
    활성화된 Demo CCTV의 MP4 영상을 반환한다.
    WEB / MOBILE에서 공통으로 사용한다.
    """

    try:
        video_path = service.get_demo_video_path(cctv_id)

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

    # 모바일용 재인코딩 파일이 있을 때만 대체합니다. 원본/Yolo 입력은 보존합니다.
    # 인증은 동일한 get_current_user()를 거치며 무관한 파일 경로를 열지 않습니다.
    if mobile_compatible:
        variant = video_path.with_name(f"{video_path.stem}_mobile{video_path.suffix}")
        if variant.is_file():
            video_path = variant

    return FileResponse(
        path=video_path,
        media_type="video/mp4",
        filename=video_path.name,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "no-store",
        },
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
        result = service.start_demo(body.scenario)

        # DEMO start activates CCTV rows directly, bypassing the ordinary
        # CCTV monitoring endpoint that enqueues auto-mapping preparation.
        # Enqueue only successfully activated DEMO CCTV after DB commit.
        # Redis/provider failures must never cancel a started DEMO session.
        try:
            from ..integrations.cctv_mapping import auto_mapping_enabled

            if auto_mapping_enabled():
                from ..workers import prewarm_context_mapping

                for cctv in result.cctvs:
                    prewarm_context_mapping.apply_async(args=(int(cctv.id),))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                "DEMO mapping prewarm scheduling unavailable: %s",
                type(exc).__name__,
            )

        return result

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
