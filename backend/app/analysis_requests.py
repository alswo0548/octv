"""
사건을 AI 판단 시스템에 넘겨주는 접수 담당 파일

이미 DB에 저장된 사건이 AI 판단이 필요한 사건인지 확인하고,
필요하면 판단 작업을 요청한다.

① CCTV에서 재난 탐지
② 사건을 PostgreSQL에 저장
③ analysis_requests.py
④ Redis → Celery Worker
⑤ LangGraph 판단
"""

import logging
import os

from fastapi import HTTPException

from .analysis_lock import (
    acquire_analysis_lock,
    release_analysis_lock,
)
from .db.session import get_connection
from .incidents.repository import find_detail


log = logging.getLogger(__name__)


# DB에서 사건을 조회 후
# 현재 AI 판단 요청이 필요한 상태인지 확인합니다.
def get_analysis_input(
    incident_id,
):
    with get_connection() as c:
        row = find_detail(
            c,
            incident_id,
        )

    if not row:
        raise HTTPException(
            404,
            "사건이 없습니다.",
        )

    if (
        row["status"]
        not in {
            "DETECTED",
            "CONFIRMED",
        }
        or row["risk_score"] is not None
    ):
        return None

    return row


# 판단이 필요하면 Celery에 작업 요청
def request_analysis(
    incident_id,
):
    incident = get_analysis_input(
        incident_id
    )

    if incident is None:
        return {
            "incident_id": incident_id,
            "queued": False,
            "reason": (
                "ALREADY_READY_OR_INACTIVE"
            ),
        }

    if (
        os.environ.get(
            "OCTV_DECISION_ENABLED",
            "0",
        )
        != "1"
    ):
        raise HTTPException(
            503,
            "판단 연결은 05번 완료 후 활성화합니다.",
        )

    # 분석 가능한 재난 유형인지 먼저 확인합니다.
    from ai.risk_priority.rules import (
        RISK_POLICIES,
    )

    if (
        incident["hazard_type"]
        not in RISK_POLICIES
    ):
        log.warning(
            "analysis_unsupported_hazard "
            "incident=%s hazard=%s",
            incident_id,
            incident["hazard_type"],
        )

        return {
            "incident_id": incident_id,
            "queued": False,
            "reason": (
                "UNSUPPORTED_HAZARD_TYPE"
            ),
        }

    lock_token = None

    try:
        # -------------------------------------------------
        # 동일 Incident 중복 Celery 등록 방지
        # -------------------------------------------------
        lock_token = acquire_analysis_lock(
            incident_id
        )

        if lock_token is None:
            return {
                "incident_id": incident_id,
                "queued": False,
                "reason": (
                    "ALREADY_QUEUED_OR_RUNNING"
                ),
            }

        from .workers import (
            analyze_incident,
        )

        # lock_token도 함께 넘깁니다.
        # Worker가 자신이 소유한 Lock만
        # 안전하게 해제하기 위해 필요합니다.
        task = analyze_incident.delay(
            incident_id,
            lock_token,
        )

    except Exception as exc:
        # Redis Lock 획득 후
        # Celery publish가 실패한 경우에는
        # Lock을 바로 제거해야 다음 탐지에서
        # 다시 분석 요청할 수 있습니다.
        if lock_token is not None:
            try:
                release_analysis_lock(
                    incident_id,
                    lock_token,
                )
            except Exception:
                log.exception(
                    "analysis_lock_release_failed "
                    "incident=%s",
                    incident_id,
                )

        log.warning(
            "analysis_publish_failed "
            "incident=%s error=%s",
            incident_id,
            type(exc).__name__,
        )

        raise HTTPException(
            503,
            (
                "판단 요청을 전달하지 못했습니다. "
                "연결 복구 후 다시 요청하세요."
            ),
        ) from None

    return {
        "incident_id": incident_id,
        "queued": True,
        "task_id": task.id,
    }


# 사건 DB 저장 완료 후 AI 판단 작업을 요청합니다.
# 판단 요청 실패가 Incident 저장 자체를
# rollback시키지는 않습니다.
def after_incident_committed(
    incident_id,
):
    if (
        os.environ.get(
            "OCTV_DECISION_ENABLED",
            "0",
        )
        != "1"
    ):
        return {
            "incident_id": incident_id,
            "queued": False,
            "reason": "DISABLED",
        }

    try:
        return request_analysis(
            incident_id
        )

    except Exception as exc:
        log.warning(
            "decision_not_queued "
            "incident=%s error=%s",
            incident_id,
            type(exc).__name__,
        )

        return {
            "incident_id": incident_id,
            "queued": False,
        }