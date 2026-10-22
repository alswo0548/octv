"""CCTV 기상 격자 + 수위 반경 관측소 선택 + 교통 링크 후보 Redis 캐시.

수위는 거리 기준의 인근 하천 관측소로만 해석하며, 도로 침수 영향권은
입증하지 않습니다. 교통 방향 미확정 값은 기존 Rule에 주입하지 않습니다.
인증키·DB·YOLO/CCTV Runtime 내부를 변경하지 않습니다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from math import cos, floor, isfinite, log, pi, sin, tan

MAPPING_VERSION = 6
MAPPING_TTL_SEC = 7 * 24 * 60 * 60
CACHE_PREFIX = "octv:context:mapping:v6:"
LOCK_PREFIX = "octv:context:mapping:lock:v6:"
KMA_WEATHER_URL = (
    "https://apis.data.go.kr/1360000/"
    "VilageFcstInfoService_2.0/getUltraSrtNcst"
)

# KMA 5km Lambert Conformal Conic 격자 변환의 공표된 상수.
_RE = 6371.00877 / 5.0
_SLAT1 = 30.0 * pi / 180
_SLAT2 = 60.0 * pi / 180
_OLON = 126.0 * pi / 180
_OLAT = 38.0 * pi / 180
_SN = log(cos(_SLAT1) / cos(_SLAT2)) / log(
    tan(pi / 4 + _SLAT2 / 2) / tan(pi / 4 + _SLAT1 / 2)
)
_SF = tan(pi / 4 + _SLAT1 / 2) ** _SN * cos(_SLAT1) / _SN
_RO = _RE * _SF / tan(pi / 4 + _OLAT / 2) ** _SN


def auto_mapping_enabled(environment=None) -> bool:
    values = os.environ if environment is None else environment
    return str(values.get("OCTV_AUTO_MAPPING_ENABLED", "0")).strip() == "1"


def kma_grid(latitude, longitude) -> tuple[int, int]:
    """위·경도(WGS84) → 기상청 5km 격자; 외부 API 호출 없음."""
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("CCTV 좌표를 확인하세요.") from None
    if not (isfinite(lat) and isfinite(lon) and -90 < lat < 90 and -180 <= lon <= 180):
        raise ValueError("CCTV 좌표 범위가 올바르지 않습니다.")
    ra = _RE * _SF / tan(pi / 4 + lat * pi / 360) ** _SN
    theta = (lon - 126.0) * pi / 180 * _SN
    # 기상청 격자 산출 예제는 정수화 시 +0.5 후 버림을 사용한다.
    return floor(ra * sin(theta) + 43.0 + 0.5), floor(_RO - ra * cos(theta) + 136.0 + 0.5)


def _fingerprint(cctv: dict) -> str:
    """CCTV ID가 같더라도 위치·지역·제공처 변경 시 캐시 무효화."""
    lat, lon = float(cctv["latitude"]), float(cctv["longitude"])
    kma_grid(lat, lon)  # 유효성 검증
    from .auto_match_providers import water_search_radius_m
    scope = [
        MAPPING_VERSION, int(cctv["id"]),
        f"{lat:.7f}", f"{lon:.7f}",
        str(cctv.get("region_code") or ""),
        str(cctv.get("provider") or ""),
        str(cctv.get("name") or cctv.get("cctv_name") or ""),
        str(cctv.get("address") or ""),
        # 사용자 정의 반경이 바뀌면 관측소 선택도 새로 계산합니다.
        water_search_radius_m(),
        auto_mapping_enabled(),
    ]
    return sha256(json.dumps(scope, ensure_ascii=True).encode("utf-8")).hexdigest()


def _redis():
    # 일반 API 응답 경로에서는 Redis 장애가 API/판단 장애로 전파되지 않게 한다.
    import redis

    return redis.Redis.from_url(
        os.environ["OCTV_REDIS_URL"],
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )


def get_cached_mapping(cctv: dict) -> dict | None:
    """좌표 지문이 맞는 검증된 캐시만 반환. Redis 장애는 cache miss."""
    try:
        fingerprint = _fingerprint(cctv)
        raw = _redis().get(f"{CACHE_PREFIX}{int(cctv['id'])}")
        if raw is None:
            return None
        result = json.loads(raw)
        grid = result.get("weather_grid")
        if (
            result.get("version") != MAPPING_VERSION
            or result.get("fingerprint") != fingerprint
            or not isinstance(grid, dict)
            or type(grid.get("nx")) is not int
            or type(grid.get("ny")) is not int
            or not 1 <= grid["nx"] <= 149
            or not 1 <= grid["ny"] <= 253
        ):
            return None
        return result
    except Exception:  # 캐시/네트워크/파싱 실패: 기존 판단 기능은 계속 진행
        return None


def prepare_cached_mapping(cctv: dict) -> str:
    """활성 CCTV의 검증 가능한 격자만 Redis에 저장; 인증키/API 조회 없음."""
    fingerprint = _fingerprint(cctv)
    if get_cached_mapping(cctv) is not None:
        return "CACHED"
    nx, ny = kma_grid(cctv["latitude"], cctv["longitude"])
    # 국내 격자 밖 데이터는 외부 API 요청을 만들지 않는다.
    if not (1 <= nx <= 149 and 1 <= ny <= 253):
        return "OUTSIDE_KMA_GRID"
    try:
        client = _redis()
        key = f"{CACHE_PREFIX}{int(cctv['id'])}"
        lock = f"{LOCK_PREFIX}{int(cctv['id'])}"
        from uuid import uuid4

        token = uuid4().hex
        if not client.set(lock, token, nx=True, ex=30):
            return "IN_PROGRESS"
        try:
            # 잠금 대기 중 다른 요청이 채웠을 수 있으므로 재확인.
            if get_cached_mapping(cctv) is not None:
                return "CACHED"
            # 인증키와 URL을 Redis로 보내지 않습니다. HTTPS 조회 오류도 기존 분석에
            # 전파하지 않으며, 추정만 가능한 대상은 NO_MAPPING으로 남깁니다.
            water_info = {"status": "RADIUS_MAPPING_NOT_PREPARED"}
            traffic_info = {"status": "NEEDS_ROAD_DIRECTION_VERIFICATION"}
            if auto_mapping_enabled():
                from .auto_match_providers import find_water_mapping, find_traffic_mapping
                water_candidate = find_water_mapping(
                    cctv, os.getenv("WATER_LEVEL_API_KEY", ""), client
                )
                traffic_candidate = find_traffic_mapping(
                    cctv, os.getenv("TRAFFIC_API_KEY", ""), client
                )
                if water_candidate["status"] in (
                        "VERIFIED_EXACT_COLOCATION", "NEARBY_STATION_WITH_THRESHOLDS",
                        "NEARBY_STATION_NO_THRESHOLDS"):
                    # 공식 관측소 좌표 + 설정 반경만을 매핑 조건으로 사용.
                    # 수위값과 공식 경보 기준은 사건 발생 시 기존 검증기가 판단.
                    water_info = water_candidate
                else:
                    water_info.update({
                        "reason": water_candidate["status"],
                        "candidates": water_candidate.get("candidates", []),
                    })
                traffic_info.update({
                    "reason": traffic_candidate["status"],
                    "candidates": traffic_candidate.get("candidates", []),
                })
            data = {
                "version": MAPPING_VERSION,
                "cctv_id": int(cctv["id"]),
                "fingerprint": fingerprint,
                "weather_grid": {"nx": nx, "ny": ny},
                "water_level": water_info,
                "traffic": traffic_info,
                "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            # 승인 오류나 키 미설정은 빠르게 재시도하고, 검토가 필요한 후보는
            # 하루간 유지해 외부기관 API를 과도하게 반복 호출하지 않습니다.
            retry_causes = {"MISSING_KEY", "API_UNAVAILABLE_OR_UNAPPROVED",
                            "API_UNAVAILABLE_OR_UNKNOWN_SCHEMA", "PROVIDER_REJECTED_941",
                            "PROVIDER_RESPONSE_ERROR", "INVALID_STATION_CATALOG",
                            "STATION_COORDINATES_UNAVAILABLE", "STATION_CATALOG_EMPTY"}
            reasons = {water_info.get("reason"), traffic_info.get("reason")}
            ttl = 600 if reasons & retry_causes else 86400
            client.set(key, json.dumps(data, ensure_ascii=True), ex=ttl)
            return "CREATED"
        finally:
            client.eval(
                "if redis.call('GET',KEYS[1]) == ARGV[1] then "
                "return redis.call('DEL',KEYS[1]) else return 0 end",
                1, lock, token,
            )
    except Exception:
        return "CACHE_UNAVAILABLE"


def weather_request_for(incident: dict) -> dict:
    """사건의 CCTV 좌표에 맞춘 기상 요청 (공식 KMA 격자, 인증값 미포함)."""
    source = {
        "id": incident["cctv_id"],
        "latitude": incident["latitude"],
        "longitude": incident["longitude"],
        "region_code": incident.get("region_code"),
        "provider": incident.get("provider", "UTIC"),
        "name": incident.get("cctv_name") or incident.get("name"),
        "address": incident.get("address"),
    }
    cached = get_cached_mapping(source)
    try:
        if cached is not None:
            nx, ny = cached["weather_grid"]["nx"], cached["weather_grid"]["ny"]
        else:
            # Redis 장애/캐시 미준비여도 수학적 격자 계산은 API 호출 없이 가능.
            nx, ny = kma_grid(source["latitude"], source["longitude"])
        if not (1 <= nx <= 149 and 1 <= ny <= 253):
            return {"mapped": False}
    except (ValueError, TypeError, OverflowError, KeyError):
        return {"mapped": False}

    return {
        "mapped": True,
        "required_env": ["WEATHER_API_KEY"],
        "publication_delay_min": 10,
        "max_age_sec": 7200,
        "url": KMA_WEATHER_URL,
        "params": {
            "serviceKey": "${WEATHER_API_KEY}",
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
            "base_date": "${KMA_BASE_DATE}",
            "base_time": "${KMA_BASE_TIME}",
            "nx": nx,
            "ny": ny,
        },
    }


def water_request_for(incident: dict) -> dict:
    """캐시에 반경 내 공식 관측소가 선택돼 있으면 10분 수위 요청 생성."""
    cctv = {
        "id": incident.get("cctv_id", incident.get("id")),
        "latitude": incident.get("latitude"),
        "longitude": incident.get("longitude"),
        "region_code": incident.get("region_code"),
        "provider": incident.get("provider", "UTIC"),
        "name": incident.get("cctv_name") or incident.get("name"),
        "address": incident.get("address"),
    }
    cached = get_cached_mapping(cctv)
    record = cached.get("water_level", {}) if cached else {}
    station = str(record.get("station_id") or "")
    if (record.get("status") not in (
            "VERIFIED_EXACT_COLOCATION", "NEARBY_STATION_WITH_THRESHOLDS",
            "NEARBY_STATION_NO_THRESHOLDS")
            or not station.isascii() or not station.isdigit() or not 5 <= len(station) <= 12):
        return {"mapped": False}
    # 파서/관측시각 검증은 기존 water_level.py / normalization.py 재사용.
    return {
        "mapped": True,
        "required_env": ["WATER_LEVEL_API_KEY"],
        "source": "HRFCO_WATERLEVEL_10M",
        "max_age_sec": 1800,
        "url": f"https://api.hrfco.go.kr/${{WATER_LEVEL_API_KEY}}/waterlevel/list/10M/{station}.json",
        "params": {},
        "spec": {
            "rows_path": ["content"], "station_key": "wlobscd",
            "station_id": station, "value_key": "wl", "time_key": "ymdhm",
            "time_format": "%Y%m%d%H%M", "timezone": "KST", "scale": 1,
        },
        "station_info": {
            "url": "https://api.hrfco.go.kr/${WATER_LEVEL_API_KEY}/waterlevel/info.json",
            "params": {},
        },
    }


def traffic_request_for(incident: dict) -> dict:
    """현재 ITS 응답에는 촬영 방향을 검증할 근거가 없어 Rule 입력은 보류.

    주행 속도만으로 정체 등급이나 통제 상태를 추정하지 않습니다.
    검증 전 후보는 mapping_reference_for()를 통해 MCP에 상태만 전달합니다.
    """
    return {}


def mapping_reference_for(incident: dict) -> dict:
    """Redis의 안전한 수위·교통 *후보 상태*를 MCP Context에 참고정보로 전달.

    Rule이 사용하는 water_level_m / water_risk_level / traffic_control 등과
    다른 필드명을 사용하며, 실제 위험도 가산 근거로 활용하지 않습니다.
    원본 API 키·URL·응답·날짜가 지난 실측값은 저장하거나 반환하지 않습니다.
    """
    cctv = {
        "id": incident.get("cctv_id", incident.get("id")),
        "latitude": incident.get("latitude"), "longitude": incident.get("longitude"),
        "region_code": incident.get("region_code"),
        "provider": incident.get("provider", "UTIC"),
        "name": incident.get("cctv_name") or incident.get("name"),
        "address": incident.get("address"),
    }
    cached = get_cached_mapping(cctv)
    result = {}
    for field, item, provider in (
        ("water_station_mapping", "water_level", "HRFCO_STATION_CATALOG"),
        ("traffic_link_mapping", "traffic", "ITS_TRAFFIC_LINK_CANDIDATES"),
    ):
        record = cached.get(item, {}) if isinstance(cached, dict) else {}
        record = record if isinstance(record, dict) else {}
        candidates = record.get("candidates", [])
        candidates = candidates if isinstance(candidates, list) else []
        # 사용자 화면 및 MCP 결과에 참고 가능한 비인증 식별자와 거리만 표시.
        safe_candidates = []
        id_key = "station_id" if item == "water_level" else "link_id"
        for row in candidates[:5]:
            if not isinstance(row, dict):
                continue
            identifier = str(row.get(id_key) or "")
            if not (identifier.isascii() and identifier.isdecimal() and 5 <= len(identifier) <= 15):
                continue
            meters = row.get("distance_m")
            if not (type(meters) is int and 0 <= meters <= 200000):
                meters = None
            safe_candidates.append({id_key: identifier, "distance_m": meters})
        confirmed_colocation = (item == "water_level" and
                               record.get("status") == "VERIFIED_EXACT_COLOCATION")
        nearby_selected = (item == "water_level" and record.get("status") in (
            "VERIFIED_EXACT_COLOCATION", "NEARBY_STATION_WITH_THRESHOLDS",
            "NEARBY_STATION_NO_THRESHOLDS"))
        # cache miss / 후보 없음 / 제공기관 오류는 동일한 정상 상태가 아닙니다.
        reason = str(record.get("reason") or record.get("status") or "CACHE_NOT_READY")
        failed = reason in {
            "PROVIDER_REJECTED_941", "PROVIDER_RESPONSE_ERROR", "MISSING_KEY",
            "API_UNAVAILABLE_OR_UNAPPROVED", "API_UNAVAILABLE_OR_UNKNOWN_SCHEMA",
            "INVALID_STATION_CATALOG", "STATION_COORDINATES_UNAVAILABLE",
        }
        status = ("ERROR" if failed else "NEARBY_STATION_SELECTED" if nearby_selected
                  else "REVIEW_REQUIRED" if safe_candidates else "NO_MAPPING")
        result[field] = {
            "value": None,
            "status": status,
            "observed_at": None,
            "source": provider,
            "unit": "mapping_status",
            "mapping_reason": reason[:80],
            "candidate_count": len(safe_candidates),
            "candidates": safe_candidates,
            "station_colocation_verified": confirmed_colocation,
            "radius_mapping_selected": nearby_selected,
            "selected_station_id": (str(record.get("station_id")) if nearby_selected else None),
            "radius_m": (record.get("radius_m") if nearby_selected else None),
            "official_thresholds_available": (record.get("thresholds_available") is True
                                              if nearby_selected else False),
            "flood_impact_verified": False,
            "road_direction_verified": False,
        }
    return result


def prepare_monitored_cctv(cctv_id: int) -> str:
    """Worker에서 DB를 읽어 현재 감시 중인 CCTV만 캐시한다."""
    from backend.app.cctvs.repository import get_cctv
    from backend.app.db.session import get_connection

    with get_connection() as connection:
        row = get_cctv(connection, int(cctv_id))
    if not row:
        return "NOT_FOUND"
    if not row["is_monitored"]:
        return "MONITORING_OFF"
    return prepare_cached_mapping(row)


def prepare_all_monitored() -> dict:
    """기상특보 자동 ON 또는 배포 후 기존 ON CCTV도 한 번에 준비."""
    from backend.app.db.session import get_connection

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, latitude, longitude, region_code, provider, name, address "
            "FROM cctvs WHERE is_monitored = TRUE ORDER BY id"
        ).fetchall()

    summary: dict[str, int] = {}
    for row in rows:
        status = prepare_cached_mapping(row)
        summary[status] = summary.get(status, 0) + 1
    return summary


WEATHER_TTL_SEC = 90
WEATHER_CACHE_PREFIX = "octv:context:weather_payload:v1:"


def _weather_key(query: dict) -> str | None:
    """KMA 공식 초단기실황 요청에만 공유 캐시 적용; 키/URL은 보관하지 않음."""
    if query.get("url") != KMA_WEATHER_URL or query.get("headers"):
        return None
    params = query.get("params") or {}
    try:
        nx, ny = int(params["nx"]), int(params["ny"])
        date, hour = str(params["base_date"]), str(params["base_time"])
        if (
            str(params.get("dataType", "")).upper() != "JSON"
            or int(params.get("pageNo", 0)) != 1
            or int(params.get("numOfRows", 0)) < 100
        ):
            return None
        if not (1 <= nx <= 149 and 1 <= ny <= 253):
            return None
        if not (len(date) == 8 and date.isdecimal() and len(hour) == 4 and hour.isdecimal()):
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return f"{WEATHER_CACHE_PREFIX}{nx}:{ny}:{date}:{hour}"


def get_cached_weather_payload(query: dict) -> dict | None:
    if not auto_mapping_enabled():
        return None
    key = _weather_key(query)
    if key is None:
        return None
    try:
        payload = json.loads(_redis().get(key) or "null")
        if not isinstance(payload, dict) or str(payload.get("response", {}).get("header", {}).get("resultCode")) != "00":
            return None
        return payload
    except Exception:
        return None


def cache_weather_payload(query: dict, payload: dict) -> None:
    """성공한 RN1/WSD 관측 항목만 90초 캐시; 오류·인증정보는 저장하지 않음."""
    if not auto_mapping_enabled():
        return
    key = _weather_key(query)
    if key is None:
        return
    try:
        response = payload["response"]
        if str(response["header"]["resultCode"]) != "00":
            return
        rows = response["body"]["items"]["item"]
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return
        selected = [
            {name: row[name] for name in ("category", "baseDate", "baseTime", "obsrValue")}
            for row in rows
            if isinstance(row, dict) and row.get("category") in ("RN1", "WSD")
        ]
        if not {row["category"] for row in selected} == {"RN1", "WSD"}:
            return
        slim = {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": {"item": selected}},
            },
        }
        text = json.dumps(slim, ensure_ascii=True)
        if len(text) > 8192:
            return
        _redis().set(key, text, ex=WEATHER_TTL_SEC)
    except Exception:
        # 캐시 실패는 정상 API 응답을 덮어쓰지 않는다.
        return
