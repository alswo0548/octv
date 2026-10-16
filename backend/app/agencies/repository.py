"""
기관 조회·LangGraph 추천 저장 및 선택 기관 전달과 DB 알림을 처리합니다.
schemas.py 가 데이터 형식 검사 후, repository.py 가 실제 PostgreSQL 에서 데이터를 조회하고 저장

파일 흐름
1. 기관 전달 시 사건 행과 추천 기관 행을 잠그고, 선택한 경로 후보를 검사합니다.
2. 새로 전달하는 기관만 DELIVERED로 변경하고 해당 기관의 활성 사용자에게 DB 알림을 생성합니다.
3. 필요한 경우 사건을 SENT로 변경하고 처리 결과를 Service에 돌려줍니다.

주요 기능
- 추천 기관·경로 소속 검사, 중복 전달 방지, COMPLETED 상태 유지
- 기존 notifications UNIQUE 제약을 이용한 알림 중복 방지
- 기존 추천·경로 데이터 조회 (LangGraph 및 지도 API 재실행 없음)

주의: 테이블·컬럼·ENUM 변경, commit/rollback, FCM 호출은 이 파일에 없습니다.
선택 경로는 검증만 하고 선택 이력을 저장하지 않습니다.
"""

from typing import Any

from fastapi import HTTPException
from .schemas import DeliverySelection


# 선택한 지역 조건을 적용하고 기관명·ID 순서로 조회합니다.
def list_agencies(connection, region_code: str | None = None):
    sql = "SELECT id, name, agency_type FROM agencies"
    params = []
    if region_code is not None:
        sql += " WHERE region_code = %s"
        params.append(region_code)
    return connection.execute(sql + " ORDER BY name, id", params).fetchall()


# LangGraph가 저장한 추천 기관과 경로후보를 DB에서 읽어오는 역할
def list_recommendations(connection, incident_id: int):
    incident = connection.execute(
        "SELECT id, status FROM incidents WHERE id = %s", (incident_id,),
    ).fetchone()
    if incident is None:
        raise HTTPException(status_code=404, detail="사건이 없습니다.")

    recommendations = connection.execute(
        """
        SELECT ar.id AS agency_recommendation_id, ar.agency_id,
               a.name AS agency_name, a.agency_type,
               ar.recommendation_rank, ar.recommendation_score,
               ar.recommendation_status, ar.score_breakdown_json, ar.rule_version
        FROM incident_agency_recommendations ar
        JOIN agencies a ON a.id = ar.agency_id
        WHERE ar.incident_id = %s
        ORDER BY ar.recommendation_rank, ar.agency_id
        """,
        (incident_id,),
    ).fetchall()
    routes = connection.execute(
        """
        SELECT r.id, r.agency_recommendation_id, r.route_name,
               r.distance_m, r.duration_sec, r.total_score, r.score_breakdown_json,
               r.disqualify_reason, r.route_path_json, r.rule_version
        FROM route_candidates r
        JOIN incident_agency_recommendations ar ON ar.id = r.agency_recommendation_id
        WHERE ar.incident_id = %s
        ORDER BY r.agency_recommendation_id,
                 (r.disqualify_reason IS NOT NULL),
                 CASE r.score_breakdown_json ->> 'verification_status'
                     WHEN 'VERIFIED' THEN 0
                     WHEN 'NEEDS_REVIEW' THEN 1
                     ELSE 2
                 END,
                 r.total_score DESC NULLS LAST, r.id
        """,
        (incident_id,),
    ).fetchall()
    # 경로를 기관별로 재조회하지 않고 이미 읽은 목록을 추천 ID 기준으로 묶습니다.
    routes_by_recommendation: dict[int, list[dict]] = {}
    for route in routes:
        routes_by_recommendation.setdefault(route["agency_recommendation_id"], []).append(route)
    return {
        "incident_id": incident_id,
        "incident_status": incident["status"],
        "items": [
            {**row, "routes": routes_by_recommendation.get(row["agency_recommendation_id"], [])}
            for row in recommendations
        ],
    }


# 하나의 DB 트랜잭션 안에서 모든 기관의 유효성을 확인하고 전달 상태·DB 알림을 저장합니다.
def save_delivery(
    connection: Any,                        # PostgreSQL 연결 객체
    incident_id: int,                       # 전달할 사건 번호
    selections: list[DeliverySelection],    # 선택한 기관 목록
) -> tuple[dict, list[int]]:                # 처리 결과 딕셔너리와 알림 ID 목록을 함께 반환
    
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    incident = _lock_deliverable_incident(connection, incident_id)
    
    validated: list[dict] = []

    # 모든 기관을 먼저 검증하며 ID 순서로 잠가 동시 요청 간 교착 가능성을 줄입니다.
    """
    DB 잠금(Lock) 이란?
    두 관리자가 동시에 같은 사건을 전달하면 DB 알림이 중복 생성될 수 있다.
    그래서 사건과 기관 추천 데이ㅓ를 잠가 다른 요청이 동시에 변경하지 못하도록 조정
    sorted() 로 기관 ID를 순서대로 처리해 동시 요청 간 충돌 가능성을 줄여주기도 한다.
    """
    for selection in sorted(selections, key=lambda item: item.agency_id):
        recommendation = _lock_recommendation(connection, incident_id, selection.agency_id)
        _validate_optional_route(connection, recommendation["id"], selection.route_candidate_id)
        if recommendation["recommendation_status"] not in (
            "RECOMMENDED", "DELIVERED", "COMPLETED",
        ):
            raise HTTPException(status_code=409, detail="처리할 수 없는 기관 전달 상태입니다.")
        validated.append(recommendation)

    items: list[dict] = []
    notification_ids: list[int] = []
    for recommendation in validated:
        # 실제 기관 전달과 알림 생성
        previous_status = recommendation["recommendation_status"]
        newly_delivered = previous_status == "RECOMMENDED"
        new_notifications: list[dict] = []
        if newly_delivered:
            # DELIVERED/COMPLETED는 다시 수정하지 않아 중복 알림과 완료 상태 초기화를 막습니다.
            connection.execute(
                """
                UPDATE incident_agency_recommendations
                SET recommendation_status = 'DELIVERED'
                WHERE id = %s AND recommendation_status = 'RECOMMENDED'
                """,
                (recommendation["id"],),
            )
            new_notifications = _create_delivery_notifications(connection, incident_id, recommendation)
            notification_ids.extend(row["id"] for row in new_notifications)
        items.append({
            "agency_id": recommendation["agency_id"],
            "agency_recommendation_id": recommendation["id"],
            "status": "DELIVERED" if newly_delivered else previous_status,
            "newly_delivered": newly_delivered,
            "created_notification_count": len(new_notifications),
        })

    # 처음 전달되거나 이미 전달된 기관이 있을 때만 CONFIRMED 사건을 SENT로 전환합니다.
    # COMPLETED 기관만 다시 선택했다면 사건을 SENT로 되돌리지 않습니다.
    incident_status = incident["status"]
    if incident_status == "CONFIRMED" and any(item["status"] == "DELIVERED" for item in items):
        connection.execute(
            "UPDATE incidents SET status = 'SENT' WHERE id = %s AND status = 'CONFIRMED'",
            (incident_id,),
        )
        incident_status = "SENT"

    # 잠금은 ID 순서로 하되 WEB에 응답할 때는 사용자가 선택한 기관 순서로 복원합니다.
    items_by_agency = {item["agency_id"]: item for item in items}
    result = {
        "incident_id": incident_id,
        "incident_status": incident_status,
        "items": [items_by_agency[selection.agency_id] for selection in selections],
        "created_notification_count": len(notification_ids),
        "push_status": "NOT_IMPLEMENTED",
    }
    # 반환된 알림 ID는 PR 3에서 commit 이후 발송 작업을 연결할 때 활용할 수 있습니다.
    return result, notification_ids


# 04번 06 코드 · 사건별 후보 기관 저장 (기존 UNIQUE 재사용) — 기존 함수·SQL 보존
from psycopg.types.json import Jsonb


def save_recommendation(connection, incident_id, recommendation):
    p = {
        **recommendation,
        'incident_id': incident_id,
        'breakdown': Jsonb(recommendation['score_breakdown_json']),
    }
    return connection.execute(
        """
        INSERT INTO incident_agency_recommendations (
            incident_id, agency_id, recommendation_rank,
            recommendation_score, score_breakdown_json, rule_version
        )
        VALUES (
            %(incident_id)s, %(agency_id)s, %(recommendation_rank)s,
            %(recommendation_score)s, %(breakdown)s, %(rule_version)s
        )
        ON CONFLICT (incident_id, agency_id)
        DO UPDATE SET
            recommendation_rank = EXCLUDED.recommendation_rank,
            recommendation_score = EXCLUDED.recommendation_score,
            score_breakdown_json = EXCLUDED.score_breakdown_json,
            rule_version = EXCLUDED.rule_version
        RETURNING *
        """,
        p,
    ).fetchone()


def list_analysis_agencies(connection):
    return connection.execute('SELECT * FROM agencies ORDER BY id').fetchall()


# 사건 행을 잠가 같은 사건의 LangGraph 결과 저장·동시 기관 전달과 충돌하지 않게 합니다.
# 역할: 사건이 존재하고 전달 가능한 상태인지 검사
def _lock_deliverable_incident(connection: Any, incident_id: int) -> dict:
    incident = connection.execute(
        "SELECT id, status FROM incidents WHERE id = %s FOR UPDATE",  # FOR UPDATE: 해당 사건 행을 잠가 다른 작업과 충돌 방지
        (incident_id,),
    ).fetchone()
    if incident is None:
        raise HTTPException(status_code=404, detail="사건이 없습니다.")
    # 감지된 사건을 임의로 확정하지 않으며 확인 또는 기존 전달된 사건만 허용합니다.
    if incident["status"] not in ("CONFIRMED", "SENT"):
        raise HTTPException(status_code=409, detail="확인된 사건만 전달할 수 있습니다.")
    return incident


# 선택 기관이 해당 사건의 추천 기관인지 확인하고 해당 관계를 잠급니다.
def _lock_recommendation(connection: Any, incident_id: int, agency_id: int) -> dict:
    recommendation = connection.execute(
        """
        SELECT id, agency_id, recommendation_status
        FROM incident_agency_recommendations
        WHERE incident_id = %s AND agency_id = %s
        FOR UPDATE
        """,
        (incident_id, agency_id),
    ).fetchone()
    if recommendation is None:
        raise HTTPException(status_code=422, detail="해당 사건의 추천 기관이 아닙니다.")
    return recommendation


# 경로 ID가 전달되면 같은 추천 기관의 제외되지 않은 후보인지 검증합니다.
def _validate_optional_route(
    connection: Any, recommendation_id: int, route_candidate_id: int | None,
) -> None:
    if route_candidate_id is None:
        return
    route = connection.execute(
        """
        SELECT id
        FROM route_candidates
        WHERE id = %s
          AND agency_recommendation_id = %s
          AND disqualify_reason IS NULL
        FOR SHARE
        """,
        # agency_recommendation_id = %s: 해당 추천 기관에 속하는 경로인지
        # disqualify_reason IS NULL: 제외 사유가 없는 경로인지
        # FOR SHARE: 다른 작업이 해당 경로를 수정하지 못하도록 공유 잠금
        (route_candidate_id, recommendation_id),
    ).fetchone()
    # FOR SHARE로 검증 후 트랜잭션 완료 전에 경로가 수정·삭제되는 위험을 줄입니다.
    if route is None:
        raise HTTPException(
            status_code=422, detail="해당 기관에 속한 제외되지 않은 경로 후보를 선택하세요.",
        )


# 새로 전달된 기관의 활성 기관 담당자·현장 출동대원에게 사용자별 DB 알림을 생성합니다.
def _create_delivery_notifications(connection: Any, incident_id: int, recommendation: dict) -> list[dict]:
    # notification_enabled=False여도 앱 내 알림은 만들며 Push 설정 필터링은 추후 작업에서 합니다.
    # 기존 UNIQUE(agency_recommendation_id, user_id)와 ON CONFLICT로 재삽입을 막습니다.
    return connection.execute(
        """
        INSERT INTO notifications (
            incidents_id, agency_id, user_id, agency_recommendation_id
        )
        SELECT %s, %s, u.id, %s
        FROM users u
        WHERE u.agency_id = %s
          AND u.is_active = TRUE
          AND u.role IN ('AGENCY_STAFF', 'RESPONDER')
        ORDER BY u.id
        ON CONFLICT (agency_recommendation_id, user_id) DO NOTHING
        RETURNING id, user_id
        """,
        (incident_id, recommendation["agency_id"],
         recommendation["id"], recommendation["agency_id"]),
    ).fetchall()

"""
1. 알림 대상 사용자가 0명이어도 기관 전달 자체는 처리됨. 대상 사용자가 반드시 있어야 한다는 조건은 두지 않았음
2. DB 알림 생성은 휴대폰 알림 발송이 아닌 notifications 테이블에 저장하는 단계고 추후 FCM을 연결해야함
"""