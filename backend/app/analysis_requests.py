"""
사건을 AI 판단 시스템에 넘겨주는 접수 담당 파일
이미 DB에 저장된 사건이 AI 판단이 필요한 사건인지 확인하고, 필요하면 판단 작업을 요청한다.

① CCTV에서 재난 탐지 
② 사건을 PostgreSQL에 저장
③ analysis_requests.py (판단 필요 여부 확인 후 작업 요청) ** 현재 파일 **
④ Redis → Celery Worker (판단 요청을 대기열에 넣고 실행)
⑤ LangGraph 판단 (위험도·우선순위·기관·경로 추천)
"""

import logging
import os

from fastapi import HTTPException
from .db.session import get_connection
from .incidents.repository import find_detail

log = logging.getLogger(__name__)


# DB에서 사건을 조회 후 사건이 존재한다면, AI가 판단해야 하는지 확인
# 이미 판단이 완료된 사건이면 추가 판단을 요청하지 않는다.('status' 값과 'risk_score' 값 확인)
def get_analysis_input(incident_id):
    with get_connection() as c:
        row = find_detail(c, incident_id)
    if not row:
        raise HTTPException(404, '사건이 없습니다.')
    if (
        row['status'] not in {'DETECTED', 'CONFIRMED'}
        or row['risk_score'] is not None
    ):
        return None
    return row


# 판단이 필요하면 Celery에 작업 요청
def request_analysis(incident_id):
    # 기존 조회 결과를 재사용해 분석 상태와 재난 유형을 함께 확인합니다.
    incident = get_analysis_input(incident_id)
    if incident is None:
        return {
            'incident_id': incident_id,
            'queued': False,
            'reason': 'ALREADY_READY_OR_INACTIVE'
        }
    if os.environ.get('OCTV_DECISION_ENABLED', '0') != '1':
        raise HTTPException(
            503,
            '판단 연결은 05번 완료 후 활성화합니다.'
        )
    try:
        # 분석을 켠 경우에만 기존 판단 정책을 읽습니다. 새 유형이나 점수는 만들지 않습니다.
        from ai.risk_priority.rules import RISK_POLICIES

        # 사건화와 판단의 유형명이 다르면 임의 변환하지 않고 요청을 건너뜁니다.
        if incident['hazard_type'] not in RISK_POLICIES:
            log.warning(
                'analysis_unsupported_hazard incident=%s hazard=%s',
                incident_id,
                incident['hazard_type'],
            )
            return {
                'incident_id': incident_id,
                'queued': False,
                'reason': 'UNSUPPORTED_HAZARD_TYPE',
            }

        from .workers import analyze_incident

        # .delay() 지금 즉시 AI 판단을 실행하는 게 아닌 Celery에 작업을 등록하라는 요청
        # CCTV 사건이 여러 개 발생하더라도 판단 작업을 대기열에 등록해 순서대로 처리할 수 있는 구조를 만듦.
        task = analyze_incident.delay(incident_id)
    except Exception as exc:
        log.warning(
            'analysis_publish_failed incident=%s error=%s',
            incident_id,
            type(exc).__name__
        )
        raise HTTPException(
            503,
            '판단 요청을 전달하지 못했습니다. 연결 복구 후 다시 요청하세요.'
        ) from None
    return {
        'incident_id': incident_id,
        'queued': True,
        'task_id': task.id
    }

# 사건 DB 저장 완료 후 AI 판단 작업을 요청합니다.
# 판단 요청이 실패하더라도 기존 사건 저장 결과는 유지합니다.
def after_incident_committed(incident_id):
    # 자동 분석 OFF는 정상 설정. 반복 탐지마다 DB 조회나 실패 경고를 만들지 않습니다.
    if os.environ.get('OCTV_DECISION_ENABLED', '0') != '1':
        return {
            'incident_id': incident_id,
            'queued': False,
            'reason': 'DISABLED',
        }

    try:
        return request_analysis(incident_id)
    except Exception as exc:
        log.warning(
            'decision_not_queued incident=%s error=%s',
            incident_id,
            type(exc).__name__
        )
        return {
            'incident_id': incident_id,
            'queued': False
        }