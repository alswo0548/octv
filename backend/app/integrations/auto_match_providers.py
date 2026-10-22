"""수위 관측소 반경 매핑과 ITS 교통정보 후보·주변 돌발정보 조회.

수위: 기본 CCTV 반경 10km, 공식 기준 수위를 가진 가까운 관측소 우선.
교통: 도로 링크/방향은 미확정이면 Rule 점수로 넘기지 않고,
      반경 1km ITS 돌발정보는 사건 Context의 참고 항목으로 전달.
인증키와 원본 URL은 Redis/출력에 저장하지 않습니다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from math import asin, cos, isfinite, radians, sin, sqrt
from hashlib import sha256
from urllib.parse import quote

import httpx

HRFCO_BASE = "https://api.hrfco.go.kr"
ITS_TRAFFIC_URL = "https://openapi.its.go.kr:9443/trafficInfo"
ITS_EVENT_URL = "https://openapi.its.go.kr:9443/eventInfo"
WATER_RADIUS_M_DEFAULT = 10_000
TRAFFIC_EVENT_RADIUS_M_DEFAULT = 1_000
EVENT_CACHE_TTL_SEC = 90
CATALOG_CACHE_KEY = "octv:context:hrfco:station_catalog:v2"
CATALOG_TTL_SECONDS = 6 * 60 * 60


def distance_m(lat1, lon1, lat2, lon2):
    """Haversine; 좌표 오류 시 유효하지 않은 후보로 간주합니다."""
    try:
        a, b, c, d = (float(x) for x in (lat1, lon1, lat2, lon2))
        if not all(isfinite(v) for v in (a, b, c, d)):
            return None
        if not (-90 <= a <= 90 and -90 <= c <= 90 and -180 <= b <= 180 and -180 <= d <= 180):
            return None
    except (TypeError, ValueError, OverflowError):
        return None
    x, y = radians(c - a), radians(d - b)
    q = sin(x / 2) ** 2 + cos(radians(a)) * cos(radians(c)) * sin(y / 2) ** 2
    return 2 * 6371008.77 * asin(min(1, sqrt(q)))


def _field(row, *names):
    if not isinstance(row, dict):
        return None
    lower = {str(key).lower(): value for key, value in row.items()}
    return next((lower[name.lower()] for name in names if name.lower() in lower), None)


def _list_from_payload(payload, primary):
    if not isinstance(payload, dict):
        return None
    # 오류 응답(예: HRFCO 941)을 비어 있는 성공 데이터로 취급하지 않습니다.
    if str(payload.get("code", "")).strip() not in ("", "0", "00"):
        return None
    rows = payload.get(primary)
    if rows is None and isinstance(payload.get("response"), dict):
        outer = payload["response"]
        code = str(outer.get("resultCode", outer.get("code", "0"))).strip()
        if code not in ("0", "00"):
            return None
        rows = outer.get(primary)
    if isinstance(rows, dict):
        rows = [rows]
    return rows if isinstance(rows, list) else None


def _safe_get_json(url, params=None, *, timeout_seconds=4.0):
    """후보 검색은 1회 요청; 실패 시 URL/키를 예외나 로그에 노출하지 않습니다.

    관측소 요청은 기존 4초, ITS 소통정보는 조회량을 고려해 12초를 사용합니다.
    """
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            response = client.get(url, params=params or {})
            if response.status_code != 200 or len(response.content) > 2_000_000:
                return None
            return response.json()
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        return None


# 한강홍수통제소 관측소 좌표는 소수점 도뿐 아니라 도-분-초(DMS) 형식으로도 제공됨.
# 경도 127-05-45.0 -> 127.095833..., 위도 37-10-56.9 -> 37.18247...
# 범위/분/초를 검증하고, 알 수 없는 형식은 위치를 추측하지 않습니다.
_DMS_COORDINATE = re.compile(r"^(\d{1,3})-(\d{1,2})-(\d{1,2}(?:\.\d+)?)$")


def _parse_station_coordinate(value, *, latitude: bool):
    if value is None or isinstance(value, bool):
        return None
    upper_bound = 90 if latitude else 180
    try:
        decimal = float(value)
    except (TypeError, ValueError, OverflowError):
        # '-'는 좌표의 부호가 아니라 도·분·초 구분자입니다.
        matched = _DMS_COORDINATE.fullmatch(str(value).strip())
        if not matched:
            return None
        degrees, minutes, seconds = (float(part) for part in matched.groups())
        if not (0 <= minutes < 60 and 0 <= seconds < 60 and degrees <= upper_bound):
            return None
        decimal = degrees + minutes / 60 + seconds / 3600
    return decimal if isfinite(decimal) and -upper_bound <= decimal <= upper_bound else None


def _canonical_station(row):
    code = str(_field(row, "wlobscd") or "").strip()
    name = str(_field(row, "obsnm", "wlobsnm") or "").strip()
    river = str(_field(row, "rvnm", "rivername") or "").strip()
    lat = _parse_station_coordinate(_field(row, "lat", "latitude"), latitude=True)
    lon = _parse_station_coordinate(_field(row, "lon", "longitude", "lng"), latitude=False)
    # 확인된 HRFCO 관측소 코드 및 유효한 위경도만 받습니다.
    if not (code.isascii() and code.isdigit() and 5 <= len(code) <= 12 and name):
        return None
    if lat is None or lon is None:
        return None
    levels = []
    for field in ("wrnwl", "almwl", "srswl"):
        try:
            levels.append(float(_field(row, field)))
        except (TypeError, ValueError, OverflowError):
            levels.append(None)
    valid_levels = (all(x is not None and isfinite(x) for x in levels)
                    and 0 <= levels[0] < levels[1] < levels[2])
    if all(value is None for value in levels) and row.get("thresholds_available") is True:
        # Redis 캐시의 원본 공식제원 확인 플래그만 복원합니다. 값을 만들지 않습니다.
        valid_levels = True
    return {"station_id": code, "name": name, "river": river,
            "latitude": lat, "longitude": lon, "thresholds_available": valid_levels}


def _name_key(value):
    return "".join(str(value or "").split()).casefold()


def configured_radius_m(environment, variable, default, minimum=100, maximum=20_000):
    """설정 미입력은 기본값, 비정상 설정값은 보수적으로 기본값을 사용."""
    try:
        raw = environment.get(variable, default)
        if isinstance(raw, bool):
            raise ValueError
        value = int(raw)
        if not minimum <= value <= maximum:
            raise ValueError
        return value
    except (TypeError, ValueError, OverflowError):
        return default


def water_search_radius_m(environment=None):
    if environment is None:
        import os
        environment = os.environ
    return configured_radius_m(environment, "OCTV_WATER_STATION_RADIUS_M",
                               WATER_RADIUS_M_DEFAULT)


def traffic_event_radius_m(environment=None):
    if environment is None:
        import os
        environment = os.environ
    return configured_radius_m(environment, "OCTV_TRAFFIC_EVENT_RADIUS_M",
                               TRAFFIC_EVENT_RADIUS_M_DEFAULT, minimum=100, maximum=5_000)


def choose_water_station(cctv, station_rows, radius_m=WATER_RADIUS_M_DEFAULT):
    """반경 내 공식 수위관측소 자동 선택.

    정책: CCTV 방향/하천명 무관, 기준 수위가 있는 가까운 관측소 우선.
    관측소 수위는 *인근 하천의 참고 위험 신호*이지 도로 침수 증거가 아님.
    """
    if not station_rows:
        return {"status": "STATION_CATALOG_EMPTY", "candidates": []}
    try:
        radius_m = int(radius_m)
        if not 100 <= radius_m <= 20_000:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        return {"status": "INVALID_SEARCH_RADIUS", "candidates": []}
    nearby, parsed_count = [], 0
    for raw in station_rows[:5000]:
        row = _canonical_station(raw)
        if row is None:
            continue
        parsed_count += 1
        meters = distance_m(cctv.get("latitude"), cctv.get("longitude"),
                            row["latitude"], row["longitude"])
        if meters is None or meters > radius_m:
            continue
        nearby.append({**row, "distance_m": round(meters)})
    if not parsed_count:
        return {"status": "STATION_COORDINATES_UNAVAILABLE", "candidates": []}
    if not nearby:
        return {"status": "NO_STATION_WITHIN_RADIUS", "radius_m": radius_m,
                "candidates": []}
    nearby.sort(key=lambda r: (r["distance_m"], r["station_id"]))
    # 주의/경보/위험 수위가 없는 관측소보다 공식 기준값 있는 관측소를 선택.
    eligible = [r for r in nearby if r["thresholds_available"]] or nearby
    selected = eligible[0]
    # 동일 위치의 별개 관측소라면 임의로 하나를 선택하지 않습니다.
    if len(eligible) > 1 and abs(selected["distance_m"] - eligible[1]["distance_m"]) <= 10:
        return {"status": "AMBIGUOUS_NEARBY_STATIONS", "radius_m": radius_m,
                "candidates": nearby[:5]}
    close_name = _name_key(cctv.get("name") or cctv.get("cctv_name"))
    verified_colocation = (selected["distance_m"] <= 50
                          and len(close_name) >= 3
                          and _name_key(selected["name"]) == close_name
                          and selected["thresholds_available"])
    status = ("VERIFIED_EXACT_COLOCATION" if verified_colocation
              else "NEARBY_STATION_WITH_THRESHOLDS" if selected["thresholds_available"]
              else "NEARBY_STATION_NO_THRESHOLDS")
    return {"status": status, "station_id": selected["station_id"],
            "distance_m": selected["distance_m"], "radius_m": radius_m,
            "thresholds_available": selected["thresholds_available"],
            "flood_impact_verified": False, "candidates": nearby[:5]}


def _read_station_catalog(redis_client, key):
    """(공식 관측소 목록, 조회 상태). 오류 코드 의미는 제공기관 확인 전 추정하지 않음."""
    if redis_client is not None:
        try:
            raw = redis_client.get(CATALOG_CACHE_KEY)
            if raw:
                rows = json.loads(raw)
                if isinstance(rows, list):
                    return rows, "OK_CACHED"
        except Exception:
            pass
    # 서비스키는 URL에 포함되므로 이 URL 자체를 Redis에 절대 저장하지 않습니다.
    payload = _safe_get_json(f"{HRFCO_BASE}/{quote(key, safe='')}/waterlevel/info.json")
    if isinstance(payload, dict):
        # 941의 정확한 원인은 공식 제공기관 확인이 필요합니다.
        code = str(payload.get("code", "")).strip()
        if code not in ("", "0", "00"):
            return None, "PROVIDER_REJECTED_941" if code == "941" else "PROVIDER_RESPONSE_ERROR"
    rows = _list_from_payload(payload, "content")
    if rows is None:
        return None, "API_UNAVAILABLE_OR_UNAPPROVED"
    if len(rows) > 5000:
        return None, "INVALID_STATION_CATALOG"
    if not rows:
        return None, "STATION_CATALOG_EMPTY"
    # 최소 필드만 저장. API 인증 문자열, HTTP URL, 원본 응답은 저장하지 않습니다.
    filtered = []
    for row in rows:
        station = _canonical_station(row)
        if station is not None:
            filtered.append({
                "wlobscd": station["station_id"], "obsnm": station["name"],
                "rvnm": station["river"], "lat": station["latitude"],
                "lon": station["longitude"],
                # 캐시된 카탈로그에서는 공식 기준 수위의 '존재 확인'만 재사용합니다.
                # 실제 수위 분류는 기존 공식 제원 API에서 재검증합니다.
                "thresholds_available": station["thresholds_available"],
            })
    # 좌표 해석 실패 시 기존처럼 빈 리스트를 6시간 저장하면 복구 후에도
    # CCTV에 '관측소 없음'으로 보이므로, 실패를 명시하고 캐시하지 않습니다.
    if not filtered:
        return None, "STATION_COORDINATES_UNAVAILABLE"
    if redis_client is not None:
        try:
            value = json.dumps(filtered, ensure_ascii=False)
            if len(value.encode("utf-8")) < 800_000:
                redis_client.set(CATALOG_CACHE_KEY, value, ex=CATALOG_TTL_SECONDS)
        except Exception:
            pass
    return filtered, "OK_FRESH"


def find_water_mapping(cctv, api_key, redis_client=None, radius_m=None):
    if not api_key:
        return {"status": "MISSING_KEY", "candidates": []}
    rows, status = _read_station_catalog(redis_client, api_key)
    if rows is None:
        return {"status": status, "candidates": []}
    return choose_water_station(cctv, rows, radius_m=radius_m or water_search_radius_m())


def _traffic_records(payload):
    """ITS JSON 응답 형식별 성공 코드 확인 후 링크 목록 추출.

    data / response.data / response.body.items.item 모두 지원합니다.
    실패 코드와 알 수 없는 형식은 빈 링크 목록으로 간주하지 않습니다.
    """
    if not isinstance(payload, dict):
        return None
    if "code" in payload and str(payload["code"]).strip() not in ("", "0", "00"):
        return None
    response = payload.get("response")
    header = response.get("header") if isinstance(response, dict) else None
    if isinstance(header, dict):
        result_code = str(header.get("resultCode", "")).strip()
        if result_code not in ("0", "00"):
            return None
    elif isinstance(response, dict) and "resultCode" in response:
        if str(response["resultCode"]).strip() not in ("0", "00"):
            return None
    if "resultCode" in payload and str(payload["resultCode"]).strip() not in ("0", "00"):
        return None
    if isinstance(payload.get("header"), dict):
        if str(payload["header"].get("resultCode", "")).strip() not in ("0", "00"):
            return None

    for scope in (payload, response):
        if not isinstance(scope, dict):
            continue
        rows = scope.get("data")
        if rows is None and isinstance(scope.get("body"), dict):
            rows = scope["body"].get("items")
        if rows is None:
            rows = scope.get("items")
        # 제공처/JSON 변환 방식에 따른 item 감싸기를 안전하게 풀어 줍니다.
        for _ in range(2):
            if isinstance(rows, dict) and "item" in rows:
                rows = rows["item"]
            else:
                break
        if isinstance(rows, dict):
            rows = [rows]
        if isinstance(rows, list):
            return rows if len(rows) <= 5000 else None
    return None


def find_traffic_mapping(cctv, api_key, redis_client=None):
    """ITS 교통 링크의 공개 범위에서 후보만 조회. 링크 좌표/촬영방향 부재는 NO_NEARBY로 오인하지 않음."""
    if not api_key:
        return {"status": "MISSING_KEY", "candidates": []}
    try:
        lat, lon = float(cctv["latitude"]), float(cctv["longitude"])
        if not all(isfinite(x) for x in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "INVALID_COORDINATES", "candidates": []}
    # 이름이 변경되면 도로명 기반 후보가 달라지므로 오래된 후보 캐시를 무효화.
    cache_seed = json.dumps({
        "id": str(cctv.get("id") or ""), "lat": f"{lat:.7f}", "lon": f"{lon:.7f}",
        "provider": str(cctv.get("provider") or ""),
        "name": str(cctv.get("name") or cctv.get("cctv_name") or ""),
        "address": str(cctv.get("address") or ""),
    }, ensure_ascii=True, sort_keys=True)
    cache_key = "octv:context:its:road_candidates:v3:" + sha256(cache_seed.encode()).hexdigest()
    if redis_client is not None:
        try:
            raw = redis_client.get(cache_key)
            if raw:
                cached = json.loads(raw)
                if isinstance(cached, dict) and cached.get("status") in (
                    "DIRECTION_UNVERIFIED", "NO_NEARBY_LINK", "LINK_GEOMETRY_UNAVAILABLE"
                ):
                    return cached
        except Exception:
            pass
    payload = _safe_get_json(ITS_TRAFFIC_URL, {
        "apiKey": api_key, "type": "all", "drcType": "all", "getType": "json",
        "minX": lon - 0.015, "maxX": lon + 0.015,
        "minY": lat - 0.015, "maxY": lat + 0.015,
    }, timeout_seconds=12.0)
    rows = _traffic_records(payload)
    if rows is None:
        return {"status": "API_UNAVAILABLE_OR_UNKNOWN_SCHEMA", "candidates": []}
    nearby, by_name = [], []
    without_geometry = 0
    camera_label = _name_key(" ".join(str(cctv.get(field) or "") for field in ("name", "address")))
    for row in rows[:5000]:
        if not isinstance(row, dict):
            continue
        section_id = _field(row, "linkid", "roadsectionid")
        if section_id is None:
            continue
        road_name = str(_field(row, "roadname") or "")[:80]
        road_direction = str(_field(row, "drctype", "roaddrctype") or "")[:30]
        geometry_distance = distance_m(lat, lon, _field(row, "coordy"), _field(row, "coordx"))
        candidate = {"link_id": str(section_id)[:60], "road_name": road_name,
                     "direction": road_direction, "distance_m": None,
                     "geometry_verified": False}
        if geometry_distance is None:
            # ITS 교통소통정보 표준 응답은 링크 좌표를 필수 제공하지 않음.
            # 도로명 일치는 검토용일 뿐 CCTV 촬영 도로/방향의 증거가 아님.
            without_geometry += 1
            label = _name_key(road_name)
            if len(label) >= 3 and label in camera_label:
                by_name.append(candidate)
            continue
        if geometry_distance <= 250:
            candidate["distance_m"] = round(geometry_distance)
            candidate["geometry_verified"] = True
            nearby.append(candidate)
    nearby.sort(key=lambda item: (item["distance_m"], item["link_id"]))
    if nearby or by_name:
        status = "DIRECTION_UNVERIFIED"
    elif without_geometry:
        status = "LINK_GEOMETRY_UNAVAILABLE"
    else:
        status = "NO_NEARBY_LINK"
    result = {"status": status, "candidates": (nearby + by_name)[:3],
              "records_without_geometry": without_geometry}
    if redis_client is not None:
        try:
            redis_client.set(cache_key, json.dumps(result, ensure_ascii=True), ex=24 * 60 * 60)
        except Exception:
            pass
    return result


_EVENT_KST = timezone(timedelta(hours=9))


def _event_date(value):
    if value is None or str(value).strip() in ("", "0", "-"):
        return None
    raw = str(value).strip()
    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, pattern).replace(tzinfo=_EVENT_KST)
        except ValueError:
            continue
    return None


def _event_window(latitude, longitude, radius_m):
    # 원형 반경을 포함하는 WGS84 사각 영역. 실제 후보는 Haversine으로 2차 검사.
    spread_lat = radius_m / 111_320 * 1.05
    spread_lon = radius_m / max(111_320 * cos(radians(latitude)), 1) * 1.05
    return {"minX": round(longitude - spread_lon, 7),
            "maxX": round(longitude + spread_lon, 7),
            "minY": round(latitude - spread_lat, 7),
            "maxY": round(latitude + spread_lat, 7)}


def find_nearby_traffic_events(cctv, api_key, redis_client=None,
                               radius_m=TRAFFIC_EVENT_RADIUS_M_DEFAULT, now=None):
    """ITS 돌발정보를 CCTV 반경으로 조회. 실제 CCTV 도로의 통제/방향은 추정하지 않음.

    인증값을 Redis에 저장하지 않으며, 성공 응답만 짧게 재사용합니다.
    """
    if not api_key:
        return {"status": "MISSING_KEY", "events": []}
    try:
        latitude, longitude = float(cctv["latitude"]), float(cctv["longitude"])
        radius_m = int(radius_m)
        if (not isfinite(latitude) or not isfinite(longitude)
                or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
                or not 100 <= radius_m <= 5000):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "INVALID_COORDINATES_OR_RADIUS", "events": []}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        return {"status": "INVALID_TIME", "events": []}
    cache_seed = f"{latitude:.6f}:{longitude:.6f}:{radius_m}"
    cache_key = "octv:context:its:nearby_events:v1:" + sha256(cache_seed.encode()).hexdigest()
    if redis_client is not None:
        try:
            raw = redis_client.get(cache_key)
            cached = json.loads(raw) if raw else None
            if isinstance(cached, dict) and cached.get("status") in (
                    "NEARBY_EVENTS_FOUND", "NO_NEARBY_EVENTS"):
                cache_time = datetime.fromisoformat(cached["checked_at_utc"])
                age = (now - cache_time).total_seconds()
                if 0 <= age <= EVENT_CACHE_TTL_SEC:
                    return cached
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            pass
        except Exception:
            pass
    params = {"apiKey": api_key, "type": "all", "eventType": "all",
              "getType": "json", **_event_window(latitude, longitude, radius_m)}
    payload = _safe_get_json(ITS_EVENT_URL, params)
    rows = _traffic_records(payload)
    if rows is None:
        return {"status": "API_UNAVAILABLE_OR_UNKNOWN_SCHEMA", "events": []}
    events, no_geometry = [], 0
    for row in rows[:5000]:
        if not isinstance(row, dict):
            continue
        meters = distance_m(latitude, longitude,
                            _field(row, "coordy", "locationdatay", "latitude"),
                            _field(row, "coordx", "locationdatax", "longitude"))
        if meters is None:
            no_geometry += 1
            continue
        if meters > radius_m:
            continue
        end = _event_date(_field(row, "enddate", "enddatetime", "eventenddate"))
        start = _event_date(_field(row, "startdate", "startdatetime", "eventstartdate"))
        current = now.astimezone(_EVENT_KST)
        if (start is not None and start > current) or (end is not None and end < current):
            continue
        event_id = str(_field(row, "eventid", "eventId", "incidentid") or "")[:60]
        road_name = str(_field(row, "roadname", "routeName") or "")[:80]
        events.append({"event_id": event_id, "distance_m": round(meters),
                       "road_name": road_name,
                       "event_type": str(_field(row, "eventtype") or "")[:40],
                       "direction": str(_field(row, "roaddrcType", "drcType") or "")[:30],
                       "link_id": str(_field(row, "linkid") or "")[:60]})
    events.sort(key=lambda row: (row["distance_m"], row["event_id"]))
    # 일부 응답에 위치정보가 없으면 0건을 '교통 이상 없음'으로 오해하지 않습니다.
    status = ("NEARBY_EVENTS_FOUND" if events
              else "EVENT_COORDINATES_UNAVAILABLE" if no_geometry
              else "NO_NEARBY_EVENTS")
    result = {"status": status, "events": events[:5],
              "nearby_total": len(events), "radius_m": radius_m,
              "records_without_geometry": no_geometry,
              "checked_at_utc": now.astimezone(timezone.utc).isoformat()}
    if redis_client is not None and status != "EVENT_COORDINATES_UNAVAILABLE":
        try:
            redis_client.set(cache_key, json.dumps(result, ensure_ascii=True),
                             ex=EVENT_CACHE_TTL_SEC)
        except Exception:
            pass
    return result


def nearby_event_measurement(query):
    """MCP Context 참고 데이터: 도로/방향 미확정 이벤트를 Rule 값으로 치환하지 않음."""
    base = {"value": None, "observed_at": None,
            "source": "ITS_NEARBY_TRAFFIC_EVENTS", "unit": "events",
            "status": "NO_MAPPING", "road_match_verified": False,
            "nearby_events": []}
    if not isinstance(query, dict) or not query.get("mapped"):
        return base
    try:
        from .cctv_mapping import _redis
        redis_client = _redis()
    except Exception:
        redis_client = None
    result = find_nearby_traffic_events(query, query.get("api_key"),
        redis_client, query.get("radius_m", TRAFFIC_EVENT_RADIUS_M_DEFAULT),
        now=query.get("now"))
    status = result["status"]
    if status in ("NEARBY_EVENTS_FOUND", "NO_NEARBY_EVENTS"):
        return {**base, "status": "REFERENCE_ONLY", "value": result["nearby_total"],
                "observed_at": result["checked_at_utc"],
                "nearby_events": result["events"], "radius_m": result["radius_m"],
                "mapping_reason": status}
    return {**base, "status": "ERROR" if status in
            ("API_UNAVAILABLE_OR_UNKNOWN_SCHEMA", "MISSING_KEY") else "NO_DATA",
            "mapping_reason": status}
