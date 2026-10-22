"""
Redis에 등록된 사건 판단 요청을 받아
실제 AI 판단 기능을 실행하는 파일

workers.py 자체가 위험도를 계산하거나
최적 기관을 직접 선택하지 않습니다.

실제 판단은 LangGraph에 맡기고,
workers.py는 Celery Task 실행 및 재시도를 담당합니다.

① 사건 DB 저장 완료
② analysis_requests.py
③ Redis
④ workers.py
⑤ LangGraph
⑥ PostgreSQL 결과 저장
"""

import logging
import os

from celery import Celery

from .config import load_environment

# 독립 Worker·Beat도 Celery 설정 전에 API와 같은 실행 설정을 읽습니다.
load_environment()


from .analysis_lock import (
    release_analysis_lock,
)


log = logging.getLogger(__name__)


# Celery
celery_app = Celery(
    "octv",
    broker=os.environ["OCTV_REDIS_URL"],
)


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,

    # Worker가 실제 작업을 끝낸 뒤 ACK
    task_acks_late=True,

    # Worker 자체가 죽으면 작업을 다시 전달
    task_reject_on_worker_lost=True,

    # 한 Worker가 작업을 과도하게 선점하지 않도록 제한
    worker_prefetch_multiplier=1,

    # 한 번의 Task 실행 시간 제한
    task_time_limit=240,

    task_publish_retry=True,

    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 2,
    },

    broker_transport_options={
        "visibility_timeout": 900,
    },

    beat_schedule={
        "octv-recover-notification-pushes": {
            "task": (
                "octv.recover_notification_pushes"
            ),
            "schedule": 60.0,
            "options": {
                "queue": "notifications",
                "expires": 55,
            },
        },
    }
    if (
        os.environ.get(
            "OCTV_PUSH_ENABLED",
            "0",
        )
        == "1"
        and os.environ.get(
            "OCTV_PUSH_RECOVERY_ENABLED",
            "0",
        )
        == "1"
    )
    else {},
)


def _release_analysis_lock_safely(
    incident_id,
    lock_token,
):
    """
    분석 완료 또는 최종 실패 시
    Redis Lock을 안전하게 제거합니다.

    Lock 해제 실패 자체 때문에
    이미 끝난 분석 Task를 실패 처리하지는 않습니다.
    """

    if not lock_token:
        return

    try:
        release_analysis_lock(
            incident_id,
            lock_token,
        )

    except Exception as exc:
        log.warning(
            "analysis_lock_release_failed "
            "incident=%s error=%s",
            incident_id,
            type(exc).__name__,
        )


# CCTV 외부 데이터 매핑 사전 준비 (분석 Worker의 기존 큐 재사용)
# API 인증·실시간 관측 조회 없음. 현재는 기상 격자만 자동 확정.
@celery_app.task(
    name="octv.prewarm_context_mapping",
    queue="analysis",
)
def prewarm_context_mapping(cctv_id: int):
    from .integrations.cctv_mapping import (
        auto_mapping_enabled,
        prepare_monitored_cctv,
    )

    if not auto_mapping_enabled():
        return {"status": "DISABLED"}
    status = prepare_monitored_cctv(cctv_id)
    return {"status": status, "cctv_id": int(cctv_id)}


@celery_app.task(
    name="octv.prewarm_all_context_mappings",
    queue="analysis",
)
def prewarm_all_context_mappings():
    from .integrations.cctv_mapping import (
        auto_mapping_enabled,
        prepare_all_monitored,
    )

    if not auto_mapping_enabled():
        return {"status": "DISABLED"}
    return prepare_all_monitored()


# ---------------------------------------------------------
# Incident AI 분석 Task
# ---------------------------------------------------------
@celery_app.task(
    bind=True,
    name="octv.analyze_incident",
    queue="analysis",
    max_retries=3,
)
def analyze_incident(
    self,
    incident_id,
    lock_token=None,
):
    # 분석 기능을 끈 상태라면
    # Lock을 남겨두지 않습니다.
    if (
        os.environ.get(
            "OCTV_DECISION_ENABLED",
            "0",
        )
        != "1"
    ):
        _release_analysis_lock_safely(
            incident_id,
            lock_token,
        )

        return {
            "incident_id": incident_id,
            "skipped": "DISABLED",
        }

    import httpx

    from psycopg import OperationalError

    from ai.config import (
        get_runtime_config,
    )
    from ai.orchestration.pipeline import (
        run_pipeline,
    )
    from ai.risk_priority.rules import (
        InsufficientContext,
    )

    try:
        result = run_pipeline(
            incident_id,
            get_runtime_config(),
        )

    except (
        httpx.HTTPError,
        OperationalError,
        InsufficientContext,
    ) as exc:

        # -------------------------------------------------
        # 재시도 가능 오류
        #
        # retry 중에는 Lock을 유지합니다.
        # 그래야 같은 Incident가 또 큐에 등록되지 않습니다.
        # -------------------------------------------------

        if (
            self.request.retries
            >= self.max_retries
        ):
            # 최대 재시도까지 실패한 경우
            # 다음 탐지에서 다시 분석을 요청할 수 있도록
            # Lock을 해제합니다.
            _release_analysis_lock_safely(
                incident_id,
                lock_token,
            )

            raise

        raise self.retry(
            exc=RuntimeError(
                type(exc).__name__
            ),
            countdown=30,
        )

    except Exception:
        # 재시도 대상으로 지정하지 않은 오류라면
        # Task는 실패시키되 Lock은 제거합니다.
        _release_analysis_lock_safely(
            incident_id,
            lock_token,
        )

        raise

    # -----------------------------------------------------
    # LangGraph 분석 정상 완료
    # -----------------------------------------------------
    _release_analysis_lock_safely(
        incident_id,
        lock_token,
    )

    return result


# ---------------------------------------------------------
# Push Notification Task
# ---------------------------------------------------------
@celery_app.task(
    bind=True,
    name="octv.send_notification_push",
    queue="notifications",
    max_retries=3,
)
def send_notification_push(
    self,
    notification_id,
):
    from .notifications.service import (
        dispatch_notification_push,
    )

    result = (
        dispatch_notification_push(
            notification_id
        )
    )

    delay = result.get(
        "retry_in"
    )

    if (
        delay is not None
        and self.request.retries
        < self.max_retries
    ):
        raise self.retry(
            exc=RuntimeError(
                "PUSH_RETRY_SCHEDULED"
            ),
            countdown=int(delay),
        )

    return result


# ---------------------------------------------------------
# Notification 복구 Task
# ---------------------------------------------------------
@celery_app.task(
    name="octv.recover_notification_pushes",
    queue="notifications",
)
def recover_notification_pushes():
    from .notifications.service import (
        recover_notification_pushes
        as recover,
    )

    return recover()