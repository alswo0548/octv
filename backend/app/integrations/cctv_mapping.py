"""CCTV 좌표 기반 기상 격자 자동 매핑 + Redis 캐시.

수위 관측소와 도로 구간/방향은 좌표 근접만으로 안전하게 확정할 수
없으므로 자동 승인하지 않는다. 기존 JSON의 검증된 매핑은 유지한다.
이 모듈은 API 인증값, DB, Runtime 내부를 변경하지 않는다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from math import cos, floor, isfinite, log, pi, sin, tan

MAPPING_VERSION = 1
MAPPING_TTL_SEC = 7 * 24 * 60 * 60
CACHE_PREFIX = "octv:context:mapping:v1:"
LOCK_PREFIX = "octv:context:mapping:lock:v1:"
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
    scope = [
        MAPPING_VERSION, int(cctv["id"]),
        f"{lat:.7f}", f"{lon:.7f}",
        str(cctv.get("region_code") or ""),
        str(cctv.get("provider") or ""),
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
        if not client.set(lock, token, nx=True, ex=15):
            return "IN_PROGRESS"
        try:
            # 잠금 대기 중 다른 요청이 채웠을 수 있으므로 재확인.
            if get_cached_mapping(cctv) is not None:
                return "CACHED"
            data = {
                "version": MAPPING_VERSION,
                "cctv_id": int(cctv["id"]),
                "fingerprint": fingerprint,
                "weather_grid": {"nx": nx, "ny": ny},
                # 미확정 관측소·도로는 OK로 사용하지 않는다.
                "water_level": {"status": "NEEDS_HYDROLOGY_VERIFICATION"},
                "traffic": {"status": "NEEDS_ROAD_DIRECTION_VERIFICATION"},
                "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            client.set(key, json.dumps(data, ensure_ascii=True), ex=MAPPING_TTL_SEC)
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
            "SELECT id, latitude, longitude, region_code, provider "
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
