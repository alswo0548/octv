"""사건 저장·중복 갱신 및 목록·상세 조회 SQL."""

from uuid import uuid4
from psycopg.types.json import Jsonb

def save_detection(connection, candidate: dict):
    params = {**candidate,
              "incident_no": "OCTV-" + uuid4().hex,
              "bbox": Jsonb(candidate["detection_bbox_json"])}
    return connection.execute("""
        INSERT INTO incidents
          (incident_no, cctv_id, hazard_type, confidence, model_version,
           detection_image_path, detection_bbox_json, dedup_key,
           detected_at, last_detected_at)
        VALUES (%(incident_no)s, %(cctv_id)s, %(hazard_type)s,
          %(confidence)s, %(model_version)s, %(detection_image_path)s,
          %(bbox)s, %(dedup_key)s, %(detected_at)s, %(detected_at)s)
        ON CONFLICT (cctv_id, hazard_type, dedup_key)
          WHERE status IN ('DETECTED', 'CONFIRMED', 'SENT')
        DO UPDATE SET last_detected_at = GREATEST(
            incidents.last_detected_at, EXCLUDED.last_detected_at)
        RETURNING *
    """, params).fetchone()


READ_SQL = """
 SELECT i.*, c.name AS cctv_name, c.latitude, c.longitude,
        c.region_code, c.provider, c.address,
        a.risk_score, a.risk_level, a.priority_score, a.priority,
        a.risk_breakdown_json, a.priority_breakdown_json, a.rule_version
 FROM incidents i
 JOIN cctvs c ON c.id = i.cctv_id
 LEFT JOIN LATERAL (
   SELECT * FROM incident_assessments a
   WHERE a.incident_id = i.id ORDER BY a.id DESC LIMIT 1
 ) a ON TRUE
"""

def incident_where(filters: dict):
    clauses, params = ["TRUE"], []
    for key, column in (("status", "i.status"), ("hazard_type", "i.hazard_type"),
                        ("priority", "a.priority"), ("region_code", "c.region_code"),
                        ("cctv_id", "i.cctv_id")):
        if filters.get(key) is not None:
            clauses.append(column + " = %s")
            params.append(filters[key])
    if filters.get("confirmed_only"):
        clauses.append("i.status IN ('CONFIRMED','SENT','RESOLVED')")
    if filters.get("active_only"):
        clauses.append("i.status IN ('DETECTED','CONFIRMED','SENT')")
    for key, operator in (("start", ">="), ("end", "<")):
        if filters.get(key) is not None:
            clauses.append("i.detected_at " + operator + " %s")
            params.append(filters[key])
    if filters.get("q"):
        clauses.append("(i.incident_no ILIKE %s OR c.name ILIKE %s)")
        params.extend(["%" + filters["q"] + "%"] * 2)
    return " AND ".join(clauses), params


def list_incidents(connection, filters: dict, page: int, page_size: int):
    where, params = incident_where(filters)
    base = READ_SQL + " WHERE " + where
    total = connection.execute(
        "SELECT count(*) AS n FROM (" + base + ") q", params
    ).fetchone()["n"]
    items = connection.execute(base + """
        ORDER BY a.priority_score DESC NULLS LAST, i.detected_at, i.id
        LIMIT %s OFFSET %s
    """, [*params, page_size, (page - 1) * page_size]).fetchall()
    return {"items": items, "total": total, "page": page, "page_size": page_size}

def find_detail(connection, incident_id: int):
    return connection.execute(READ_SQL + " WHERE i.id = %s", (incident_id,)).fetchone()
