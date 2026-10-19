"""탐지 후보 검증·저장과 사건 목록·상세·상태 변경을 처리합니다.
get_connection은 backend/app/db/session.py에 있으며,
정상 종료 시 commit·예외 시 rollback합니다."""

from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from ..analysis_requests import after_incident_committed
from ..db.session import get_connection
from . import repository


# 입력 시각을 UTC로 환산한 후
# DB의 TIMESTAMP 형식에 맞춥니다.
def utc_naive(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "탐지 시각에는 시간대가 필요합니다."
        )

    return (
        value.astimezone(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
    )


# 내부 탐지 후보를 검증하고 저장합니다.
# 별도의 POST API는 아닙니다.
def register_detection(
    candidate: dict,
):
    confidence = float(
        candidate["confidence"]
    )

    if not 0 <= confidence <= 1:
        raise ValueError(
            "confidence는 0~1입니다."
        )

    data = {
        **candidate,
        "confidence": confidence,
        "detected_at": utc_naive(
            candidate["detected_at"]
        ),
    }

    with get_connection() as connection:
        incident = (
            repository.save_detection(
                connection,
                data,
            )
        )

    # 기존 사건을 DB 저장 후 마무리가 아닌 저장 후 자동 분석 연결할수있게 설정
    after_incident_committed(incident["id"])

    return incident


# DB 행을 API 응답용으로 변환합니다.
def serialize_incident(
    row,
):
    item = dict(
        row
    )

    # DB에는 UTC naive timestamp로 저장합니다.
    # API에서는 UTC offset을 명시합니다.
    for key in (
        "detected_at",
        "last_detected_at",
        "representative_image_updated_at",
    ):
        if item.get(key) is not None:
            item[key] = (
                item[key]
                .replace(
                    tzinfo=timezone.utc
                )
                .isoformat()
            )

    for key in (
        "confidence",
        "latitude",
        "longitude",
        "risk_score",
        "priority_score",
    ):
        if item.get(key) is not None:
            item[key] = float(
                item[key]
            )

    # 사건 처리 상태와
    # AI 상세 분석 완료 여부는 별도입니다.
    item["analysis_status"] = (
        "READY"
        if item.get(
            "risk_level"
        )
        else "PENDING"
    )

    return jsonable_encoder(
        item
    )


def list_incidents(
    page=1,
    page_size=5,
    filters=None,
    user=None,
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    values = dict(
        filters or {}
    )

    # 클라이언트가 임의로 넘긴 기관 조건을 버리고
    # 현재 로그인 사용자의 기관으로 결정합니다.
    values.pop(
        "agency_id",
        None,
    )

    values.pop(
        "agency_active_only",
        None,
    )

    if (
        user["role"]
        != "CONTROL_ADMIN"
    ):
        values["agency_id"] = (
            user.get(
                "agency_id"
            )
        )

        values[
            "agency_active_only"
        ] = values.get(
            "active_only",
            False,
        )

    with get_connection() as connection:
        result = (
            repository.list_incidents(
                connection,
                values,
                page,
                page_size,
            )
        )

    result["items"] = [
        serialize_incident(
            row
        )
        for row
        in result["items"]
    ]

    return result


def get_incident(
    incident_id: int,
    user: dict,
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    with get_connection() as connection:

        if (
            user["role"]
            != "CONTROL_ADMIN"
        ):
            agency_id = (
                user.get(
                    "agency_id"
                )
            )

            if agency_id is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "조회할 수 없는 사건입니다."
                    ),
                )

            access = (
                repository.find_agency_access(
                    connection,
                    incident_id,
                    agency_id,
                )
            )

            if access is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "조회할 수 없는 사건입니다."
                    ),
                )

        row = (
            repository.find_detail(
                connection,
                incident_id,
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    return serialize_incident(
        row
    )


def get_incident_image(
    incident_id: int,
    user: dict,
):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    with get_connection() as connection:

        if (
            user["role"]
            != "CONTROL_ADMIN"
        ):
            agency_id = (
                user.get(
                    "agency_id"
                )
            )

            if agency_id is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "조회할 수 없는 사건입니다."
                    ),
                )

            access = (
                repository.find_agency_access(
                    connection,
                    incident_id,
                    agency_id,
                )
            )

            if access is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "조회할 수 없는 사건입니다."
                    ),
                )

        row = (
            repository.find_representative_image(
                connection,
                incident_id,
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    if (
        row["representative_image"]
        is None
    ):
        raise HTTPException(
            status_code=404,
            detail=(
                "저장된 대표 이미지가 없습니다."
            ),
        )

    return bytes(
        row[
            "representative_image"
        ]
    )


def _require_control_admin(
    user: dict | None,
) -> None:
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    if (
        user.get("role")
        != "CONTROL_ADMIN"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "관제 관리자 권한이 필요합니다."
            ),
        )


def _find_status_or_404(
    connection,
    incident_id: int,
):
    row = repository.find_status(
        connection,
        incident_id,
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    return row


def _find_detail_or_404(
    connection,
    incident_id: int,
):
    row = repository.find_detail(
        connection,
        incident_id,
    )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="사건이 없습니다.",
        )

    return row


# ------------------------------------------------------------
# DETECTED → CONFIRMED
#
# 관제 담당자가 목록에서 사건을 클릭해 확인한 시점에 호출합니다.
#
# 이미 CONFIRMED/SENT/RESOLVED라면
# 더 낮은 상태로 되돌리지 않고 현재 상태를 그대로 반환합니다.
# ------------------------------------------------------------
def confirm_incident(
    incident_id: int,
    user: dict,
):
    _require_control_admin(
        user
    )

    with get_connection() as connection:

        current = (
            _find_status_or_404(
                connection,
                incident_id,
            )
        )

        current_status = (
            current["status"]
        )

        if (
            current_status
            == "FALSE_POSITIVE"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "오탐 처리된 사건은 "
                    "사건 확인 상태로 변경할 수 없습니다."
                ),
            )

        if (
            current_status
            == "DETECTED"
        ):
            changed = (
                repository.update_status(
                    connection,
                    incident_id,
                    "CONFIRMED",
                    (
                        "DETECTED",
                    ),
                )
            )

            # 동시에 다른 상태 변경이 있었다면
            # 현재 상태를 다시 확인합니다.
            if changed is None:
                current = (
                    _find_status_or_404(
                        connection,
                        incident_id,
                    )
                )

                if (
                    current["status"]
                    == "FALSE_POSITIVE"
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "오탐 처리된 사건은 "
                            "사건 확인 상태로 "
                            "변경할 수 없습니다."
                        ),
                    )

        row = (
            _find_detail_or_404(
                connection,
                incident_id,
            )
        )

    return serialize_incident(
        row
    )


# ------------------------------------------------------------
# DETECTED / CONFIRMED → FALSE_POSITIVE
#
# SENT 이후에는 이미 기관 전달이 완료된 사건이므로
# 여기서 단순 오탐 상태로 변경하지 않습니다.
# ------------------------------------------------------------
def mark_false_positive(
    incident_id: int,
    user: dict,
):
    _require_control_admin(
        user
    )

    with get_connection() as connection:

        current = (
            _find_status_or_404(
                connection,
                incident_id,
            )
        )

        current_status = (
            current["status"]
        )

        if (
            current_status
            == "FALSE_POSITIVE"
        ):
            row = (
                _find_detail_or_404(
                    connection,
                    incident_id,
                )
            )

            return serialize_incident(
                row
            )

        if current_status not in (
            "DETECTED",
            "CONFIRMED",
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "현재 상태에서는 "
                    "오탐 처리할 수 없습니다."
                ),
            )

        changed = (
            repository.update_status(
                connection,
                incident_id,
                "FALSE_POSITIVE",
                (
                    "DETECTED",
                    "CONFIRMED",
                ),
            )
        )

        if changed is None:
            current = (
                _find_status_or_404(
                    connection,
                    incident_id,
                )
            )

            if (
                current["status"]
                != "FALSE_POSITIVE"
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "사건 상태가 변경되어 "
                        "오탐 처리할 수 없습니다."
                    ),
                )

        row = (
            _find_detail_or_404(
                connection,
                incident_id,
            )
        )

    return serialize_incident(
        row
    )


# ------------------------------------------------------------
# CONFIRMED → SENT
#
# 이 함수 자체는 기관 전송을 수행하지 않습니다.
# 실제 기관 전달 기능이 성공한 뒤
# 사건 상태를 기록할 때 호출합니다.
# ------------------------------------------------------------
def mark_sent(
    incident_id: int,
    user: dict,
):
    _require_control_admin(
        user
    )

    with get_connection() as connection:

        current = (
            _find_status_or_404(
                connection,
                incident_id,
            )
        )

        current_status = (
            current["status"]
        )

        if (
            current_status
            == "SENT"
        ):
            row = (
                _find_detail_or_404(
                    connection,
                    incident_id,
                )
            )

            return serialize_incident(
                row
            )

        if (
            current_status
            != "CONFIRMED"
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "사건 확인(CONFIRMED) 상태에서만 "
                    "전달 완료로 변경할 수 있습니다."
                ),
            )

        changed = (
            repository.update_status(
                connection,
                incident_id,
                "SENT",
                (
                    "CONFIRMED",
                ),
            )
        )

        if changed is None:
            current = (
                _find_status_or_404(
                    connection,
                    incident_id,
                )
            )

            if (
                current["status"]
                != "SENT"
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "사건 상태가 변경되어 "
                        "전달 완료 처리할 수 없습니다."
                    ),
                )

        row = (
            _find_detail_or_404(
                connection,
                incident_id,
            )
        )

    return serialize_incident(
        row
    )