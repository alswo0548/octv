"""
LangGraph가 저장한 경로를 가져오기 전에 누가 조회하는지 확인하고, 경로 상태를 구분해서 반환하는 역할

호출 흐름: JWT 사용자 → 현재 사건/추천·전달 여부 확인 → 기존 경로 SQL 조회 → 안전 상태 표시.
관리자는 추천된 기관의 후보를 조회하고, 기관 사용자는 전달받은 자기 기관의 경로만 조회.
"""

from typing import Any

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas


def _valid_path(path: Any) -> bool:
    """지도·내비 화면에 넘길 최소한의 GeoJSON 경로 형태를 확인."""
    return (
        isinstance(path, dict)
        and path.get("type") == "LineString"
        and isinstance(path.get("coordinates"), list)
        and len(path["coordinates"]) >= 2
    )


# DB에서 조회한 경로 하나를 받아 화면에서 사용하기 좋은 데이터로 정리
def _to_candidate(row: dict) -> schemas.RouteCandidateResponse:
    """DB에 저장된 확인 상태와 제외 사유를 화면용 필드로 변환합니다."""
    breakdown = row.get("score_breakdown_json")
    status = breakdown.get("verification_status") if isinstance(breakdown, dict) else None
    # 기존 경로 검증 기준을 충족, 추가 확인 필요, 제외 대상, 검증 상태 정보가 없거나 알 수 없음
    if status not in ("VERIFIED", "NEEDS_REVIEW", "DISQUALIFIED"):
        status = None

    excluded = row.get("disqualify_reason") is not None or status == "DISQUALIFIED"
    # 네비게이션 사용 가능 여부 확인
    navigation_available = (
        not excluded
        and status in ("VERIFIED", "NEEDS_REVIEW")
        and _valid_path(row.get("route_path_json"))
    )
    # 화면에 전달할 데이터 생성
    return schemas.RouteCandidateResponse.model_validate({
        **row,
        "verification_status": status,
        "requires_review": not excluded and (
            status != "VERIFIED" or not navigation_available
        ),
        "navigation_available": navigation_available,
    })


def list_candidates(
    incident_id: int, agency_id: int, user: dict | None,
) -> schemas.RouteCandidatesResponse:
    """인증된 사용자에게 허용된 기관의 저장 경로만 반환합니다."""
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if user.get("is_active") is not True:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    # 관리자와 기관 사용자 구분
    is_admin = user.get("role") == "CONTROL_ADMIN"
    if not is_admin:
        if (
            user.get("role") not in ("AGENCY_STAFF", "RESPONDER")
            or user.get("agency_id") != agency_id
        ):
            raise HTTPException(status_code=404, detail="조회할 수 없는 경로입니다.")

    # DB 연결 후 사건, 추천 상태 조회
    with get_connection() as connection:
        scope = repository.find_route_scope(connection, incident_id, agency_id)
        if scope is None:
            raise HTTPException(status_code=404, detail="조회할 수 없는 사건입니다.")

        # 실제 전달된 기관인지 검사
        recommendation_status = scope["recommendation_status"]
        if not is_admin and recommendation_status not in ("DELIVERED", "COMPLETED"):
            raise HTTPException(status_code=404, detail="조회할 수 없는 경로입니다.")

        has_assessment = bool(scope["has_assessment"])
        if not has_assessment:
            result_status = "NOT_ANALYZED"
            candidates = []
        elif scope["recommendation_id"] is None:
            result_status = "NO_RECOMMENDATION"
            candidates = []
        else:
            rows = repository.list_candidates(connection, incident_id, agency_id)
            candidates = [_to_candidate(row) for row in rows]
            if not candidates:
                result_status = "NO_ROUTES"
            elif all(
                route.disqualify_reason is not None
                or route.verification_status == "DISQUALIFIED"
                for route in candidates
            ):
                result_status = "ALL_DISQUALIFIED"
            elif any(
                route.verification_status == "VERIFIED" and route.navigation_available
                for route in candidates
            ):
                result_status = "AVAILABLE"
            else:
                result_status = "NEEDS_REVIEW"

    return schemas.RouteCandidatesResponse.model_validate({
        "incident_id": incident_id,
        "agency_id": agency_id,
        "analysis_status": "READY" if has_assessment else "PENDING",
        "recommendation_status": recommendation_status,
        "result_status": result_status,
        "items": candidates,
    })
