"""통합관제 Dashboard Service."""

from datetime import (
    datetime,
    time,
    timedelta,
    timezone,
)
from zoneinfo import ZoneInfo
from math import isfinite

from fastapi import HTTPException

from ..db.session import get_connection
from . import repository, schemas


KST = ZoneInfo(
    "Asia/Seoul"
)


class DashboardIncidentNotFoundError(
    LookupError
):
    """Dashboard 외부상황 기준 사건을 찾지 못한 경우."""


def _today_utc_range() -> tuple[
    datetime,
    datetime,
]:
    """한국시간 오늘 범위를 UTC naive로 변환한다."""

    today_kst = datetime.now(
        KST
    ).date()

    start_kst = datetime.combine(
        today_kst,
        time.min,
        tzinfo=KST,
    )

    end_kst = (
        start_kst
        + timedelta(
            days=1
        )
    )

    start_utc = (
        start_kst
        .astimezone(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
    )

    end_utc = (
        end_kst
        .astimezone(
            timezone.utc
        )
        .replace(
            tzinfo=None
        )
    )

    return (
        start_utc,
        end_utc,
    )


def _utc_naive_to_kst(
    value: datetime,
) -> datetime:
    """DB의 UTC naive timestamp를 KST로 변환한다."""

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        KST
    )


def _kst_naive_to_aware(
    value: datetime,
) -> datetime:
    """weather_alerts KST naive timestamp를 aware KST로 변환한다."""

    if value.tzinfo is None:
        return value.replace(
            tzinfo=KST
        )

    return value.astimezone(
        KST
    )


def _unmapped_metric(
    unit: str,
) -> schemas.DashboardExternalMetric:
    """외부 API/MCP 연결 전 기본 응답."""

    return schemas.DashboardExternalMetric(
        value=None,
        unit=unit,
        observed_at=None,
        status="NO_MAPPING",
    )


def _saved_context(incident: dict) -> tuple[dict, datetime | None]:
    """Stored LangGraph context only. No provider calls or risk recalculation."""
    risk = incident.get("risk_breakdown_json") or {}
    if not isinstance(risk, dict):
        return {}, None
    snapshot = risk.get("context_snapshot") or {}
    if not isinstance(snapshot, dict):
        return {}, None
    measurements = snapshot.get("measurements") or {}
    if not isinstance(measurements, dict):
        measurements = {}
    captured = snapshot.get("captured_at")
    if isinstance(captured, str):
        try:
            captured = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        except ValueError:
            captured = None
    if not isinstance(captured, datetime):
        captured = None
    # Context captured_at is UTC. Never mistake a naive UTC timestamp for KST.
    if captured is not None and captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    return measurements, captured


def _saved_metric(measurements: dict, name: str, unit: str,
                  captured: datetime | None) -> schemas.DashboardExternalMetric:
    item = measurements.get(name)
    if not isinstance(item, dict):
        return _unmapped_metric(unit)
    raw_status = str(item.get("status") or "NO_DATA").upper()
    aliases = {
        "NOT_CONFIGURED": "NO_MAPPING", "NOT_APPLICABLE": "NO_MAPPING",
        "PENDING": "NO_DATA", "UNAVAILABLE": "NO_DATA",
        "FAILED": "ERROR", "MISSING": "NO_DATA",
    }
    allowed = {"OK", "NO_MAPPING", "NO_DATA", "STALE", "TIMEOUT", "ERROR", "INVALID"}
    status = aliases.get(raw_status, raw_status)
    if status not in allowed:
        status = "NO_DATA"
    value = item.get("value")
    # Only finite measured values with status OK. Never use 0 as a fallback.
    if status == "OK" and (isinstance(value, bool) or not isinstance(value, (int, float))
                           or not isfinite(value)):
        status = "INVALID"
    observed = item.get("observed_at")
    if isinstance(observed, str):
        try:
            observed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError:
            observed = None
    if isinstance(observed, datetime) and observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    # A measurement's own timestamp is more precise than snapshot capture time.
    if not isinstance(observed, datetime):
        observed = captured
    return schemas.DashboardExternalMetric(
        value=value if status == "OK" else None, unit=unit,
        observed_at=observed, status=status,
    )


def _mapping_state(incident: dict) -> dict[str, str]:
    """Read verified mapping; clearly label DEMO-only fallback as simulated."""
    try:
        from ..integrations.cctv_mapping import auto_mapping_enabled, get_cached_mapping
        if not auto_mapping_enabled():
            return {"weather": "AUTO_MAPPING_DISABLED", "water": "AUTO_MAPPING_DISABLED",
                    "traffic": "AUTO_MAPPING_DISABLED"}

        # The approved DEMO reference is a display-only overlay. It is never
        # persisted to Redis as official data or consumed by actual risk rules.
        from ..demo_v5_media.mapping import demo_preview_for_incident, WATER_READY
        demo = demo_preview_for_incident(incident)

        cctv = {
            "id": incident["cctv_id"],
            "latitude": incident.get("latitude"),
            "longitude": incident.get("longitude"),
            "region_code": incident.get("region_code"),
            "provider": incident.get("provider"),
            "name": incident.get("cctv_name"),
            "address": incident.get("address"),
        }
        cached = get_cached_mapping(cctv)
        if cached is None:
            if demo:
                return {"weather": "GRID_READY", "water": "DEMO_SIMULATION",
                        "traffic": "DEMO_SIMULATION"}
            return {"weather": "CACHE_NOT_READY", "water": "CACHE_NOT_READY",
                    "traffic": "CACHE_NOT_READY"}

        water = str((cached.get("water_level") or {}).get("status") or "NO_MAPPING")
        traffic = str((cached.get("traffic") or {}).get("status") or "NO_MAPPING")
        if demo:
            # Retain verified, real water station mapping where available.
            # Unverified traffic links must not masquerade as closures.
            if water not in WATER_READY:
                water = "DEMO_SIMULATION"
            traffic = "DEMO_SIMULATION"
        return {"weather": "GRID_READY", "water": water, "traffic": traffic}
    except Exception:
        return {"weather": "CACHE_UNAVAILABLE", "water": "CACHE_UNAVAILABLE",
                "traffic": "CACHE_UNAVAILABLE"}


def _role_scope(
    user: dict,
) -> tuple[bool, int | None]:
    """
    Dashboard 조회 범위를 결정한다.

    CONTROL_ADMIN:
        전체 조회

    AGENCY_STAFF / RESPONDER:
        자신의 agency_id에 전달된 사건만 조회
    """

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="로그인이 필요합니다.",
        )

    if user["role"] == "CONTROL_ADMIN":
        return (
            False,
            None,
        )

    return (
        True,
        user.get(
            "agency_id"
        ),
    )


def get_dashboard(
    page: int = 1,
    page_size: int = 5,
    user: dict | None = None,
) -> schemas.DashboardResponse:
    """
    W02 통합관제 화면 데이터를 반환한다.

    - CONTROL_ADMIN: 전체 현황
    - AGENCY_STAFF / RESPONDER:
      소속 기관에 전달된 사건 범위
    - 사건 목록과 지도는 동일한 incidents.items 사용
    - 오늘 등록 사건은 한국 날짜 기준
    - 사건 탐지 시각은 KST(+09:00)로 반환
    """

    agency_scoped, agency_id = (
        _role_scope(
            user
        )
    )

    (
        today_start_utc,
        today_end_utc,
    ) = _today_utc_range()

    with get_connection() as connection:
        summary = (
            repository.get_dashboard_summary(
                connection,
                today_start_utc=(
                    today_start_utc
                ),
                today_end_utc=(
                    today_end_utc
                ),
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        total = (
            repository.count_dashboard_incidents(
                connection,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        incidents = (
            repository.list_dashboard_incidents(
                connection,
                page=page,
                page_size=page_size,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

    total_pages = (
        (
            total
            + page_size
            - 1
        )
        // page_size
        if total > 0
        else 0
    )

    incident_items = []

    for incident in incidents:
        incident_data = {
            **incident,
            "detected_at":
                _utc_naive_to_kst(
                    incident[
                        "detected_at"
                    ]
                ),
        }

        incident_items.append(
            schemas.DashboardIncident(
                **incident_data
            )
        )

    return schemas.DashboardResponse(
        summary=(
            schemas.DashboardSummary(
                **summary
            )
        ),

        incidents=(
            schemas.DashboardIncidentPage(
                items=incident_items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=(
                    total_pages
                ),
            )
        ),
    )


def get_overview_external_status(
    user: dict | None = None,
) -> schemas.DashboardOverviewExternalStatusResponse:
    """
    W02에서 사건을 선택하지 않았을 때
    표시할 전체 외부 상황을 반환한다.

    CONTROL_ADMIN:
    - 현재 감시 범위의 활성 기상특보
    - 전체 ALERT 모드 집중감시 CCTV 수

    AGENCY_STAFF / RESPONDER:
    - 자기 기관에 전달된 진행 사건 범위의
      활성 기상특보 / 집중감시 CCTV 수

    전체 화면에서는 지역마다 값이 다른
    강수량 / 수위를 표시하지 않는다.

    도로통제는 외부 연동 전까지
    NO_MAPPING으로 반환한다.
    """

    agency_scoped, agency_id = (
        _role_scope(
            user
        )
    )

    with get_connection() as connection:
        weather_rows = (
            repository.list_overview_weather_alerts(
                connection,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        focused_count = (
            repository.count_overview_focused_monitoring_cctvs(
                connection,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

    weather_alerts = [
        schemas.DashboardWeatherAlert(
            external_alert_id=(
                row[
                    "external_alert_id"
                ]
            ),
            alert_type=(
                row[
                    "alert_type"
                ]
            ),
            alert_level=(
                row[
                    "alert_level"
                ]
            ),
            title=(
                row[
                    "title"
                ]
            ),
            issued_at=(
                _kst_naive_to_aware(
                    row[
                        "issued_at"
                    ]
                )
            ),
            region_code=(
                row[
                    "region_code"
                ]
            ),
        )

        for row in weather_rows
    ]

    return (
        schemas.DashboardOverviewExternalStatusResponse(
            last_received_at=None,

            weather_alerts=(
                weather_alerts
            ),

            road_control_count=(
                _unmapped_metric(
                    "count"
                )
            ),

            focused_monitoring_cctv_count=(
                focused_count
            ),
        )
    )


def get_external_status(
    incident_id: int,
    user: dict | None = None,
    *,
    live: bool = False,
) -> schemas.DashboardExternalStatusResponse:
    """
    선택한 사건 기준 W02 외부 상황 정보를 반환한다.

    CONTROL_ADMIN:
    - 전체 사건 접근 가능

    AGENCY_STAFF / RESPONDER:
    - 자기 기관에 DELIVERED / COMPLETED된 사건만 접근 가능

    - 기상특보와 집중감시 CCTV는 기존 DB 조회
    - 강수량·수위·차단 차로는 최근 저장된 분석 관측 스냅샷만 조회
    - 실시간 수집/자동매핑 검증은 별도로 표시, 도로통제와 차단 차로 구분
    """

    agency_scoped, agency_id = (
        _role_scope(
            user
        )
    )

    with get_connection() as connection:
        incident = (
            repository.get_external_status_incident(
                connection,
                incident_id,
                agency_id=agency_id,
                agency_scoped=agency_scoped,
            )
        )

        if incident is None:
            raise (
                DashboardIncidentNotFoundError(
                    f"incident_id={incident_id}"
                )
            )

        weather_rows = (
            repository.list_active_weather_alerts(
                connection,
                incident[
                    "region_code"
                ],
            )
        )

        focused_count = (
            repository.count_focused_monitoring_cctvs(
                connection,
                incident[
                    "region_code"
                ],
            )
        )

    weather_alerts = [
        schemas.DashboardWeatherAlert(
            external_alert_id=(
                row[
                    "external_alert_id"
                ]
            ),
            alert_type=(
                row[
                    "alert_type"
                ]
            ),
            alert_level=(
                row[
                    "alert_level"
                ]
            ),
            title=(
                row[
                    "title"
                ]
            ),
            issued_at=(
                _kst_naive_to_aware(
                    row[
                        "issued_at"
                    ]
                )
            ),
            region_code=(
                row[
                    "region_code"
                ]
            ),
        )

        for row in weather_rows
    ]

    measurements, captured = _saved_context(incident)
    mapping = _mapping_state(incident)
    from ..demo_v5_media.mapping import demo_preview_for_incident
    demo_preview = demo_preview_for_incident(incident)
    data_source = "SAVED_SNAPSHOT"
    live_checked_at = None
    if live:
        # Access was verified above; never trigger a provider call for a hidden
        # or unauthorized incident. This does not recalculate risk or write DB.
        from .live_external import latest_context
        latest, status, live_checked_at = latest_context(int(incident["id"]))
        if status == "OK" and latest is not None:
            measurements = latest.measurements
            captured = latest.captured_at
            data_source = "LIVE_MCP"
        else:
            data_source = "SAVED_FALLBACK"

    from .live_external import nearby_reference_count
    traffic_reference_count = nearby_reference_count(measurements)

    return (
        schemas.DashboardExternalStatusResponse(
            incident_id=(
                incident[
                    "id"
                ]
            ),
            incident_no=(
                incident[
                    "incident_no"
                ]
            ),
            cctv_id=(
                incident[
                    "cctv_id"
                ]
            ),
            cctv_name=(
                incident[
                    "cctv_name"
                ]
            ),
            region_code=(
                incident[
                    "region_code"
                ]
            ),
            region_name=(
                incident[
                    "region_name"
                ]
            ),
            last_received_at=captured,
            external_data_source=data_source,
            live_checked_at=live_checked_at,
            nearby_traffic_event_count=traffic_reference_count,
            weather_alerts=(
                weather_alerts
            ),
            rainfall_mm=_saved_metric(measurements, "rainfall_mm", "mm", captured),
            water_level_m=_saved_metric(measurements, "water_level_m", "m", captured),
            # blocked_lane_count is not an official road-control count.
            road_control_count=_unmapped_metric("count"),
            blocked_lane_count=_saved_metric(measurements, "blocked_lane_count", "count", captured),
            mapping_state=mapping,
            demo_mapping_preview=demo_preview,
            focused_monitoring_cctv_count=(
                focused_count
            ),
        )
    )

def get_integration_evidence(user: dict) -> dict:
    """Read-only evidence of past external-data/storage results, not an API health probe.

    A saved DB record proves neither current provider availability nor FCM delivery.
    No credential is returned and no live request is made from this endpoint.
    """
    if not user or user.get("role") != "CONTROL_ADMIN":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM weather_alerts) AS weather_count,
                    (SELECT COUNT(*) FROM route_candidates) AS route_count,
                    (SELECT COUNT(*) FROM notifications) AS notification_count
            """)
            counts = cursor.fetchone()
            cursor.execute("""
                SELECT risk_breakdown_json FROM incident_assessments
                WHERE risk_breakdown_json IS NOT NULL
                ORDER BY id DESC LIMIT 40
            """)
            assessments = cursor.fetchall()

    def evidence(count: int, positive: str, missing: str) -> dict:
        return {"status": "RECORDED" if count else "NOT_VERIFIED",
                "detail": positive if count else missing}

    observed: dict[str, int] = {"rainfall_mm": 0, "water_level_m": 0,
                                "blocked_lane_count": 0}
    for row in assessments:
        saved = row["risk_breakdown_json"] or {}
        snapshot = saved.get("context_snapshot") if isinstance(saved, dict) else None
        measurements = snapshot.get("measurements") if isinstance(snapshot, dict) else None
        if not isinstance(measurements, dict):
            continue
        for key in observed:
            item = measurements.get(key)
            if isinstance(item, dict) and item.get("status") == "OK":
                observed[key] += 1

    weather = evidence(counts["weather_count"], "기상특보 DB 기록 존재 · 현재 API 응답은 별도 확인",
                       "기상특보 DB 기록 없음 · API 응답 확인 필요")
    water = evidence(observed["water_level_m"], "수위 분석 관측 기록 존재 · 현재 API 응답은 별도 확인",
                     "수위 유효 관측 기록 없음 · 승인·매핑·API 확인 필요")
    traffic = evidence(observed["blocked_lane_count"],
                       "차단 차로 분석 기록 존재 · 도로통제 API 응답은 별도 확인",
                       "차단 차로 관측 기록 없음 · 도로/방향 매핑 확인 필요")
    kakao = evidence(counts["route_count"],
                     "경로 DB 저장 기록 존재 · 카카오 실시간 API 응답은 별도 확인",
                     "경로 DB 기록 없음 · 경로 생성·API 확인 필요")
    fcm = evidence(counts["notification_count"],
                   "앱 내 알림 DB 저장 기록 존재 · FCM 발송 및 수신은 별도 확인",
                   "앱 내 알림 DB 기록 없음 · FCM 검증 전")
    return {"weather": weather, "water": water, "traffic": traffic,
            "kakao": kakao, "fcm": fcm,
            "disclaimer": "저장된 기록은 현재 API 정상 응답이나 모바일 푸시 수신을 보장하지 않습니다."}
