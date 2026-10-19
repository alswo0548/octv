
"""
추가 지원요청의 권한 확인과 저장·조회 흐름을 담당하는 Service.

주요 기능
1. JWT로 확인된 로그인 사용자의 역할·활성 상태 검사
2. 관리자와 현장 사용자의 사건 조회 권한 구분
3. 현장 사용자는 자신에게 전달된 진행 중 사건에만 지원요청 등록
4. Repository를 통해 요청 저장·조회 후 Schema 형식으로 반환
5. DB UTC 시각을 API 응답에 맞게 변환

전체 흐름
Router → Service(권한·상태 검사) → Repository(DB 조회·저장)
→ Service(응답 변환) → Router

주의사항
- 요청 작성자 ID와 기관 ID는 로그인 사용자 정보로 결정
- 기관별 COMPLETED 상태 변경 및 사건 RESOLVED 전환은 구현하지 않음
- 지원요청은 자동 출동 지령이나 기관 자동 배정이 아님
"""


from datetime import timezone

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas


def _scope_or_404(connection, incident_id: int, user: dict):
    """관리자는 사건 전체, 기관 사용자는 전달받은 자기 기관만 허용합니다."""
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")
    role = user.get("role")
    if role == "CONTROL_ADMIN":
        agency_id = None
    elif role in ("AGENCY_STAFF", "RESPONDER"):
        agency_id = user.get("agency_id")
        if not isinstance(agency_id, int) or agency_id <= 0:
            raise HTTPException(status_code=404, detail="조회할 수 없는 사건입니다.")
    else:
        raise HTTPException(status_code=403, detail="지원 요청 조회 권한이 없습니다.")

    scope = repository.find_access_scope(connection, incident_id, agency_id)
    if scope is None or (
        role != "CONTROL_ADMIN"
        and scope["recommendation_status"] not in ("DELIVERED", "COMPLETED")
    ):
        # 타 기관 사용자에게 사건 존재 여부를 노출하지 않습니다.
        raise HTTPException(status_code=404, detail="조회할 수 없는 사건입니다.")
    return scope, agency_id


def _response(row: dict) -> schemas.SupportRequestResponse:
    """기존 DB TIMESTAMP(UTC naive)를 API의 명시적인 UTC 시각으로 바꿉니다."""
    item = dict(row)
    timestamp = item["created_at"]
    if timestamp.tzinfo is None:
        item["created_at"] = timestamp.replace(tzinfo=timezone.utc)
    else:
        item["created_at"] = timestamp.astimezone(timezone.utc)
    return schemas.SupportRequestResponse.model_validate(item)


def list_support_requests(
    incident_id: int, user: dict | None = None
) -> list[schemas.SupportRequestResponse]:
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    with get_connection() as connection:
        _scope, agency_id = _scope_or_404(connection, incident_id, user)
        rows = repository.list_for_incident(connection, incident_id, agency_id)
    return [_response(row) for row in rows]


def create_support_request(
    incident_id: int, body: schemas.SupportRequestCreate, user: dict | None = None
) -> schemas.SupportRequestResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    if user.get("role") not in ("AGENCY_STAFF", "RESPONDER"):
        raise HTTPException(status_code=403, detail="현장 기관 사용자만 요청할 수 있습니다.")
    with get_connection() as connection:
        scope, agency_id = _scope_or_404(connection, incident_id, user)
        # 기존 COMPLETED 상태를 되돌리거나 완료된 사건에 새 요청을 만들지 않습니다.
        if scope["incident_status"] != "SENT" or scope["recommendation_status"] != "DELIVERED":
            raise HTTPException(status_code=409, detail="현재 사건 또는 기관 상태에서는 요청할 수 없습니다.")
        row = repository.insert_request(
            connection, incident_id, user["id"], agency_id, body.model_dump()
        )
        if row is None:
            raise HTTPException(status_code=409, detail="사건 또는 전달 상태가 변경됐습니다. 목록을 다시 조회해주세요.")
    return _response(row)
