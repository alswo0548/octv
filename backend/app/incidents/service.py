"""탐지 후보 검증·저장과 사건 목록·상세 조회를 처리합니다.
get_connection은 backend/app/db/session.py에 있으며, 정상 종료 시 commit·예외 시 rollback합니다."""

from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from ..db.session import get_connection
from . import repository


# 입력 시각을 UTC로 환산한 후 DB의 TIMESTAMP 형식에 맞춥니다.
def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("탐지 시각에는 시간대가 필요합니다.")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


# 내부 탐지 후보를 검증하고 저장합니다. 별도의 POST API는 아닙니다.
def register_detection(candidate: dict):
    confidence = float(candidate["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError("confidence는 0~1입니다.")
    data = {
        **candidate,
        "confidence": confidence,
        "detected_at": utc_naive(candidate["detected_at"]),
    }
    with get_connection() as connection:
        incident = repository.save_detection(connection, data)
    # with 블록이 정상 종료되어 commit된 결과를 반환합니다.
    return incident


# DB 행을 복사해 시각·숫자·분석 상태를 API 응답용으로 변환합니다.
def serialize_incident(row):
    item = dict(row)
    # DB에 저장된 UTC 시각을 API 응답 형식으로 변환합니다. 한국 시간 표시는 프론트엔드에서 처리합니다. 
    for key in (
        "detected_at",
        "last_detected_at",
        "representative_image_updated_at",
    ):
        if item.get(key) is not None:
            item[key] = item[key].replace(tzinfo=timezone.utc).isoformat()
    for key in ("confidence", "latitude", "longitude", "risk_score", "priority_score"):
        if item.get(key) is not None:
            item[key] = float(item[key])
    item["analysis_status"] = "READY" if item.get("risk_level") else "PENDING"
    return jsonable_encoder(item)


# Repository의 목록 결과를 응답용으로 변환하고 페이지 정보를 유지합니다.
def list_incidents(page=1, page_size=5, filters=None, user=None):
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    values = dict(filters or {})
    # 요청에 섞인 기관 조건을 버리고, 현재 사용자 정보로 조회 범위를 정합니다.
    values.pop("agency_id", None)
    values.pop("agency_active_only", None)
    if user["role"] != "CONTROL_ADMIN":
        values["agency_id"] = user.get("agency_id")
        values["agency_active_only"] = values.get("active_only", False)
    with get_connection() as connection:
        result = repository.list_incidents(connection, values, page, page_size)
    result["items"] = [serialize_incident(row) for row in result["items"]]
    return result


def get_incident(incident_id: int, user: dict):
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    with get_connection() as connection:
        # 기관에 실제 전달된 사건인지 먼저 확인합니다. 인증 자체는 기존 auth가 담당합니다.
        if user["role"] != "CONTROL_ADMIN":
            agency_id = user.get("agency_id")
            if agency_id is None:
                raise HTTPException(404, "조회할 수 없는 사건입니다.")
            access = repository.find_agency_access(connection, incident_id, agency_id)
            if access is None:
                raise HTTPException(404, "조회할 수 없는 사건입니다.")
        row = repository.find_detail(connection, incident_id)
    if row is None:
        raise HTTPException(404, "사건이 없습니다.")
    return serialize_incident(row)

def get_incident_image(incident_id: int, user: dict):
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")

    with get_connection() as connection:
        if user["role"] != "CONTROL_ADMIN":
            agency_id = user.get("agency_id")

            if agency_id is None:
                raise HTTPException(404, "조회할 수 없는 사건입니다.")

            access = repository.find_agency_access(
                connection,
                incident_id,
                agency_id,
            )

            if access is None:
                raise HTTPException(404, "조회할 수 없는 사건입니다.")

        row = repository.find_representative_image(
            connection,
            incident_id,
        )

    if row is None:
        raise HTTPException(404, "사건이 없습니다.")

    if row["representative_image"] is None:
        raise HTTPException(404, "저장된 대표 이미지가 없습니다.")

    return bytes(row["representative_image"])