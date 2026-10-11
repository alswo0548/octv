"""사건 저장·중복 갱신과 목록·상세 조회 SQL을 실행합니다.
Service에서 받은 연결을 사용하며, 트랜잭션은 Service의 get_connection 블록이 관리합니다."""

from uuid import uuid4
from psycopg.types.json import Jsonb


# 새 사건을 저장하거나, 같은 진행 사건의 최근 탐지 시각만 갱신합니다.
def save_detection(connection, candidate: dict):
    params = {
        **candidate,
        "incident_no": "OCTV-" + uuid4().hex,
        "bbox": Jsonb(candidate["detection_bbox_json"]),
    }
    # 중복 시 최초 정보는 유지하고, 과거 탐지로 최근 시각이 되돌아가지 않게 합니다.
    return connection.execute(
        """
        INSERT INTO incidents (
            incident_no, cctv_id, hazard_type, confidence, model_version,
            detection_image_path, detection_bbox_json, dedup_key,
            detected_at, last_detected_at
        )
        VALUES (
            %(incident_no)s, %(cctv_id)s, %(hazard_type)s,
            %(confidence)s, %(model_version)s, %(detection_image_path)s,
            %(bbox)s, %(dedup_key)s, %(detected_at)s, %(detected_at)s
        )
        ON CONFLICT (cctv_id, hazard_type, dedup_key)
            WHERE status IN ('DETECTED', 'CONFIRMED', 'SENT')
        DO UPDATE SET
            last_detected_at = GREATEST(
                incidents.last_detected_at, EXCLUDED.last_detected_at
            )
        RETURNING *
        """,
        params,
    ).fetchone()


# 각 사건에 최신 평가 1건을 붙이며, 평가가 없어도 사건은 조회합니다.
READ_SQL = """
SELECT
    i.*, c.name AS cctv_name, c.latitude, c.longitude,
    c.region_code, c.provider, c.address,
    a.risk_score, a.risk_level, a.priority_score, a.priority,
    a.risk_breakdown_json, a.priority_breakdown_json, a.rule_version
FROM incidents i
JOIN cctvs c
    ON c.id = i.cctv_id
LEFT JOIN LATERAL (
    SELECT *
    FROM incident_assessments a
    WHERE a.incident_id = i.id
    ORDER BY a.id DESC
    LIMIT 1
) a ON TRUE
"""


# 검색 조건과 바인딩할 값을 같은 순서로 구성합니다.
def incident_where(filters: dict):
    clauses, params = ["TRUE"], []
    for key, column in (
        ("status", "i.status"),
        ("hazard_type", "i.hazard_type"),
        ("priority", "a.priority"),
        ("region_code", "c.region_code"),
        ("cctv_id", "i.cctv_id"),
    ):
        if filters.get(key) is not None:
            clauses.append(column + " = %s")
            params.append(filters[key])
    if filters.get("confirmed_only"):
        clauses.append("i.status IN ('CONFIRMED','SENT','RESOLVED')")
    if filters.get("active_only"):
        clauses.append("i.status IN ('DETECTED','CONFIRMED','SENT')")
    # 기간은 시작 시각을 포함하고 종료 시각은 제외합니다.
    for key, operator in (("start", ">="), ("end", "<")):
        if filters.get(key) is not None:
            clauses.append("i.detected_at " + operator + " %s")
            params.append(filters[key])
    if filters.get("q"):
        clauses.append("(i.incident_no ILIKE %s OR c.name ILIKE %s)")
        params.extend(["%" + filters["q"] + "%"] * 2)
    return " AND ".join(clauses), params


# 인증 사용자 기관의 전달 관계로 범위를 제한하며, EXISTS로 중복 행을 방지합니다.
def agency_filter(filters: dict):
    if "agency_id" not in filters:
        return "TRUE", []
    # 기관 미지정 사용자가 전체 사건을 보지 않도록 0건 조건을 반환합니다.
    if filters["agency_id"] is None:
        return "FALSE", []
    # 활성 목록은 DELIVERED만, 일반 조회는 COMPLETED 이력도 포함합니다.
    status_clause = "ar.recommendation_status IN ('DELIVERED', 'COMPLETED')"
    if filters.get("agency_active_only"):
        status_clause = "ar.recommendation_status = 'DELIVERED'"
    clause = (
        """EXISTS (
            SELECT 1
            FROM incident_agency_recommendations ar
            WHERE ar.incident_id = i.id
              AND ar.agency_id = %s
              AND
        """
        + status_clause
        + ")"
    )
    return clause, [filters["agency_id"]]


# 전체 건수와 현재 페이지에 같은 조회 조건을 적용합니다.
def list_incidents(connection, filters: dict, page: int, page_size: int):
    where, params = incident_where(filters)
    scoped_where, scoped_params = agency_filter(filters)
    where = "(" + where + ") AND (" + scoped_where + ")"
    params += scoped_params
    base = READ_SQL + " WHERE " + where
    total = connection.execute(
        "SELECT count(*) AS n FROM (" + base + ") q", params
    ).fetchone()["n"]
    # 동점일 때 탐지 시각·ID로 순서를 고정하고, 평가가 없는 사건은 뒤에 둡니다.
    items = connection.execute(
        base + """
        ORDER BY a.priority_score DESC NULLS LAST, i.detected_at, i.id
        LIMIT %s
        OFFSET %s
        """,
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# Service가 상세 조회 전에 사용할 사건·기관의 전달 관계를 반환합니다.
def find_agency_access(connection, incident_id: int, agency_id: int):
    return connection.execute(
        """
        SELECT id
        FROM incident_agency_recommendations
        WHERE incident_id = %s
          AND agency_id = %s
          AND recommendation_status IN ('DELIVERED', 'COMPLETED')
        """,
        (incident_id, agency_id),
    ).fetchone()


def find_detail(connection, incident_id: int):
    return connection.execute(READ_SQL + " WHERE i.id = %s", (incident_id,)).fetchone()
