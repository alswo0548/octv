"""
Redis에 등록된 사건 판단 요청을 받아서 실제 AI 판단 기능을 실행하는 파일

오해하지 말것! 
workers.py 자체가 위험도를 계산하거나 최적의 기관을 선택하는게 아니며,
실제 판단은 LangGraph 함수에 맡기고, worker.py 는 그 작업을 실행하고 오류가 발생하면 재시도하는 역할. 

① 사건 DB 저장 완료 (사건 ID: 31)
② analysis_requests.py (31번 사건 판단 요청)
③ Redis (판단 요청을 대기열에 보관)
④ workers.py (31번 사건을 받아 판단 함수 실행) ** 현재 파일 **
⑤ LangGraph 판단 시스템 (위험도 → 우선순위 → 기관·경로 추천)
⑥ 기존 PostgreSQL DB (판단 결과 저장)
"""


import os
from celery import Celery

# Celery : 파이썬에서 시간이 걸리는 작업을 백그라운드로 처리하도록 도와주는 도구
celery_app=Celery(
    'octv',
    broker=os.environ['OCTV_REDIS_URL']
)
celery_app.conf.update(
    task_serializer="json",                 # 요청 데이터를 JSON 형태로 전송
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,                    # 작업이 끝난 후 처리 확인
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,           # Worker가 작업을 미리 과도하게 가져오는 것 제한
    task_time_limit=240,                    # 작업 실행 시간 최대 240초
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,                   # 지정된 일시적 오류 시 최대 3번 재시도
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 2,
    },
    broker_transport_options={
        "visibility_timeout": 900,
    },
    beat_schedule={},
)

# Redis 대기열에서 Worker가 사건을 가지고 오면 실행됨.
# queue='analysis'는 여러 작업 대기열 중 사건 판단용 대기열 사용을 의미.
@celery_app.task(
    bind=True,
    name='octv.analyze_incident',
    queue='analysis',
    max_retries=3
)
def analyze_incident(self,incident_id):
    if os.environ.get('OCTV_DECISION_ENABLED','0')!='1':            # AI 판단 기능을 실행할 준비가 되었는지 확인하는 코드
        return {'incident_id':incident_id,'skipped':'DISABLED'}
    
    # 아래 실제 판단 함수는 추후 작성합니다.
    import httpx
    from psycopg import OperationalError
    from ai.config import get_runtime_config
    from ai.orchestration.pipeline import run_pipeline
    from ai.risk_priority.rules import InsufficientContext
    try:
        return run_pipeline(incident_id,get_runtime_config())
    # 판단 중 오류 발생 시 재시도
    except (
        httpx.HTTPError,
        OperationalError,
        InsufficientContext
    ) as exc:
        # URL·API 키가 들어갈 수 있는 원문 예외를 Task 로그에 넘기지 않습니다.
        raise self.retry(
            exc=RuntimeError(type(exc).__name__),
            countdown=30
        )