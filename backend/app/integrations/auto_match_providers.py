"""외부기관 자료에서 CCTV의 수위·교통 *후보*를 자동 탐색합니다.

- CCTV ID만으로 하천 영향권 또는 실제 카메라 촬영 방향을 알 수는 없습니다.
- 따라서 좌표 근접만으로 수위/도로 위험을 정상(OK)으로 확정하지 않습니다.
- 수위는 공식 관측소 명칭이 CCTV 명칭과 정확히 맞고 현장에 인접한
  매우 제한된 경우에만 자동 연결합니다. 교통은 방향 정보가 없으면 후보로만 둡니다.
- 인증키와 요청 URL은 절대 Redis/출력에 저장하지 않습니다.
"""

from __future__ import annotations

import json
from math import asin, cos, isfinite, radians, sin, sqrt
from hashlib import sha256
from urllib.parse import quote

import httpx

HRFCO_BASE = "https://api.hrfco.go.kr"
ITS_TRAFFIC_URL = "https://openapi.its.go.kr:9443/trafficInfo"
CATALOG_CACHE_KEY = "octv:context:hrfco:station_catalog:v1"
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


def _safe_get_json(url, params=None):
    """후보 검색은 1회 요청·4초 제한; 실패 시 URL/키를 예외나 로그에 노출하지 않습니다."""
    try:
        with httpx.Client(timeout=4.0, follow_redirects=False) as client:
            response = client.get(url, params=params or {})
            if response.status_code != 200 or len(response.content) > 2_000_000:
                return None
            return response.json()
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        return None


def _canonical_station(row):
    code = str(_field(row, "wlobscd") or "").strip()
    name = str(_field(row, "obsnm", "wlobsnm") or "").strip()
    river = str(_field(row, "rvnm", "rivername") or "").strip()
    latitude = _field(row, "lat", "latitude")
    longitude = _field(row, "lon", "longitude", "lng")
    # 확인된 HRFCO 관측소 코드 형식만 받습니다.
    if not (code.isascii() and code.isdigit() and 5 <= len(code) <= 12 and name):
        return None
    if distance_m(latitude, longitude, latitude, longitude) is None:
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):
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


def choose_water_station(cctv, station_rows):
    """후보 자동 검색 + 현장 일치 증거가 부족하면 자동 확정하지 않습니다."""
    stations = []
    for raw in station_rows[:5000]:
        row = _canonical_station(raw)
        if row is None:
            continue
        meters = distance_m(cctv.get("latitude"), cctv.get("longitude"),
                            row["latitude"], row["longitude"])
        if meters is None or meters > 3000:
            continue
        stations.append({**row, "distance_m": round(meters)})
    stations.sort(key=lambda row: row["distance_m"])
    nearby = stations[:3]
    # 이름이 완전히 일치하고, 50m 이내이며, 공식 기준 수위가 있어야 후보 승인.
    # 이 조건이 충족되지 않으면 주변 하천이 같다고 가정하지 않습니다.
    exact_name = _name_key(cctv.get("name") or cctv.get("cctv_name"))
    trusted = [row for row in stations if row["distance_m"] <= 50
               and row["thresholds_available"] and len(_name_key(row["name"])) >= 3
               and _name_key(row["name"]) == exact_name]
    if len(trusted) == 1:
        return {"status": "VERIFIED_EXACT_COLOCATION", "station_id": trusted[0]["station_id"],
                "distance_m": trusted[0]["distance_m"], "candidates": nearby}
    return {"status": "REVIEW_REQUIRED" if nearby else "NO_NEARBY_STATION",
            "candidates": nearby}


def _read_station_catalog(redis_client, key):
    if redis_client is not None:
        try:
            raw = redis_client.get(CATALOG_CACHE_KEY)
            if raw:
                rows = json.loads(raw)
                if isinstance(rows, list):
                    return rows
        except Exception:
            pass
    # 서비스키는 URL에 포함되므로 이 URL 자체를 Redis에 절대 저장하지 않습니다.
    payload = _safe_get_json(f"{HRFCO_BASE}/{quote(key, safe='')}/waterlevel/info.json")
    rows = _list_from_payload(payload, "content")
    if rows is None:
        return None
    if len(rows) > 5000:
        return None
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
    if redis_client is not None:
        try:
            value = json.dumps(filtered, ensure_ascii=False)
            if len(value.encode("utf-8")) < 800_000:
                redis_client.set(CATALOG_CACHE_KEY, value, ex=CATALOG_TTL_SECONDS)
        except Exception:
            pass
    return filtered


def find_water_mapping(cctv, api_key, redis_client=None):
    if not api_key:
        return {"status": "MISSING_KEY", "candidates": []}
    rows = _read_station_catalog(redis_client, api_key)
    if rows is None:
        return {"status": "API_UNAVAILABLE_OR_UNAPPROVED", "candidates": []}
    return choose_water_station(cctv, rows)


def _traffic_records(payload):
    if not isinstance(payload, dict):
        return None
    data = _list_from_payload(payload, "data")
    if data is not None:
        return data
    # 다른 제공 형식은 API 문서·실제 응답을 확인할 때까지 연결하지 않습니다.
    return None


def find_traffic_mapping(cctv, api_key, redis_client=None):
    """ITS 도로/방향 후보 조회. 카메라 촬영 방향이 DB에 없어 위험 판단 연결은 보류."""
    if not api_key:
        return {"status": "MISSING_KEY", "candidates": []}
    try:
        lat, lon = float(cctv["latitude"]), float(cctv["longitude"])
        if not all(isfinite(x) for x in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "INVALID_COORDINATES", "candidates": []}
    cache_seed = f"{cctv.get('id')}:{lat:.7f}:{lon:.7f}:{cctv.get('provider', '')}"
    cache_key = "octv:context:its:road_candidates:v1:" + sha256(cache_seed.encode()).hexdigest()
    if redis_client is not None:
        try:
            raw = redis_client.get(cache_key)
            if raw:
                cached = json.loads(raw)
                if isinstance(cached, dict) and cached.get("status") in ("DIRECTION_UNVERIFIED", "NO_NEARBY_LINK"):
                    return cached
        except Exception:
            pass
    payload = _safe_get_json(ITS_TRAFFIC_URL, {
        "apiKey": api_key, "type": "all", "drcType": "all", "getType": "json",
        "minX": lon - 0.015, "maxX": lon + 0.015,
        "minY": lat - 0.015, "maxY": lat + 0.015,
    })
    rows = _traffic_records(payload)
    if rows is None:
        return {"status": "API_UNAVAILABLE_OR_UNKNOWN_SCHEMA", "candidates": []}
    nearby = []
    for row in rows[:5000]:
        if not isinstance(row, dict):
            continue
        section_id = _field(row, "linkid", "roadsectionid")
        meters = distance_m(lat, lon, _field(row, "coordy"), _field(row, "coordx"))
        if section_id is None or meters is None or meters > 250:
            continue
        nearby.append({"link_id": str(section_id)[:60],
                       "road_name": str(_field(row, "roadname") or "")[:80],
                       "direction": str(_field(row, "drctype", "roaddrctype") or "")[:30],
                       "distance_m": round(meters)})
    nearby.sort(key=lambda item: item["distance_m"])
    # 도로명·방향·구간이 공식 자료에 있더라도, CCTV가 어느 방향을 촬영하는지
    # DB에서 확인되지 않으므로 scope_verified를 만들어내지 않습니다.
    result = {"status": "DIRECTION_UNVERIFIED" if nearby else "NO_NEARBY_LINK",
              "candidates": nearby[:3]}
    if redis_client is not None:
        try:
            redis_client.set(cache_key, json.dumps(result, ensure_ascii=True), ex=24 * 60 * 60)
        except Exception:
            pass
    return result
