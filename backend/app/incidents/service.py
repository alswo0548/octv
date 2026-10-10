"""사건 후보 검증·저장과 목록·상세 응답 변환."""

from datetime import datetime, timezone
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from ..db.session import get_connection
from . import repository

def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("탐지 시각에는 시간대가 필요합니다.")
    return value.astimezone(timezone.utc).replace(tzinfo=None)

def register_detection(candidate: dict):
    confidence = float(candidate["confidence"])
    if not 0 <= confidence <= 1:
        raise ValueError("confidence는 0~1입니다.")
    data = {**candidate, "confidence": confidence,
            "detected_at": utc_naive(candidate["detected_at"])}
    with get_connection() as connection:
        incident = repository.save_detection(connection, data)
    return incident  # with 종료 후이므로 이미 commit됨

def serialize_incident(row):
    item = dict(row)
    for key in ("detected_at", "last_detected_at"):
        item[key] = row[key].replace(tzinfo=timezone.utc).isoformat()
    for key in ("confidence", "latitude", "longitude", "risk_score", "priority_score"):
        if item.get(key) is not None:
            item[key] = float(item[key])
    item["analysis_status"] = "READY" if item.get("risk_level") else "PENDING"
    return jsonable_encoder(item)

def list_incidents(page=1, page_size=5, filters=None):
    with get_connection() as connection:
        result = repository.list_incidents(connection, filters or {}, page, page_size)
    result["items"] = [serialize_incident(row) for row in result["items"]]
    return result

def get_incident(incident_id: int):
    with get_connection() as connection:
        row = repository.find_detail(connection, incident_id)
    if row is None:
        raise HTTPException(404, "사건이 없습니다.")
    return serialize_incident(row)
