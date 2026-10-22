"""한강홍수통제소 수위 API 1회 또는 관측소 지정 시 2회 읽기 전용 진단.

실행: .venv\\Scripts\\python -X utf8 -m scripts.check_water_provider
옵션: --station-id 1018683 (info 성공 및 동일 관측소 확인 후 10분자료 1회 추가)
DB/Redis/기상/교통/YOLO는 전혀 건드리지 않습니다. 인증키/URL/전체 응답은 출력하지 않습니다.
"""

from __future__ import annotations

import argparse
import json
import os
from math import isfinite
from urllib.parse import quote

from scripts import check_context_connections as diag


def _has_successful_response(payload):
    if not isinstance(payload, dict):
        return False
    code = str(payload.get("code", "")).strip()
    return code in ("", "0", "00") and isinstance(payload.get("content"), list)


def _safe_level(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) and result >= 0 else None


def _station_thresholds(row):
    values = [_safe_level(row.get(field, row.get(field.upper())))
              for field in ("wrnwl", "almwl", "srswl")]
    if any(value is None for value in values) or not values[0] < values[1] < values[2]:
        return {"status": "UNAVAILABLE_OR_INVALID"}
    return {"status": "VALID_OFFICIAL_STATION_DATA", "caution_m": values[0],
            "warning_m": values[1], "danger_m": values[2]}


def check_water(key, station_id=None):
    """승인 여부 추정 없이 정확한 제공기관 코드와 값 존재 유무만 확인."""
    if not key:
        return {"status": "MISSING_WATER_LEVEL_API_KEY"}
    if station_id is not None and not (station_id.isascii() and station_id.isdigit()
                                       and 5 <= len(station_id) <= 12):
        return {"status": "INVALID_STATION_ID"}

    url = f"https://api.hrfco.go.kr/{quote(key, safe='')}/waterlevel/info.json"
    info, payload = diag.request_once(url)
    result = {"status": "INFO_REQUESTED", "station_info": info}
    if not _has_successful_response(payload):
        code = diag.api_status(payload).get("code")
        result["status"] = "PROVIDER_RESPONSE_ERROR" if code is not None else "INFO_UNAVAILABLE_OR_SCHEMA_UNKNOWN"
        result["provider_code"] = code
        result["meaning"] = "UNVERIFIED_BY_PROVIDER"  # 941의 원인은 추측하지 않음
        return result

    rows = payload["content"]
    result["status"] = "STATION_LIST_RECEIVED"
    result["station_count"] = len(rows)
    if station_id is None:
        return result
    matches = [row for row in rows if isinstance(row, dict)
               and str(row.get("wlobscd", row.get("WLOBSCD", ""))).strip() == station_id]
    if len(matches) != 1:
        result["station_match"] = "NOT_FOUND" if not matches else "AMBIGUOUS"
        return result

    row = matches[0]
    result["station_match"] = "EXACT_STATION_ID"
    result["thresholds"] = _station_thresholds(row)
    level_url = (f"https://api.hrfco.go.kr/{quote(key, safe='')}/"
                 f"waterlevel/list/10M/{station_id}.json")
    measured, data = diag.request_once(level_url)
    result["observations_request"] = measured
    if not _has_successful_response(data):
        result["observation_status"] = "API_ERROR_OR_SCHEMA_UNKNOWN"
        result["observation_provider_code"] = diag.api_status(data).get("code")
        return result

    station_rows = [r for r in data["content"] if isinstance(r, dict)
                    and str(r.get("wlobscd", r.get("WLOBSCD", ""))).strip() == station_id]
    valid = [(str(r.get("ymdhm", "")), _safe_level(r.get("wl"))) for r in station_rows]
    valid = [(at, value) for at, value in valid if len(at) == 12 and at.isdigit()
             and value is not None]
    if not valid:
        result["observation_status"] = "NO_VALID_STATION_OBSERVATION"
        return result
    last_time, level = max(valid)
    result["observation_status"] = "MEASUREMENT_RECEIVED_NOT_YET_FRESHNESS_VALIDATED"
    result["latest_observed_at_kst"] = last_time
    result["water_level_m"] = level
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station-id", default=None, help="공식 관측소 코드. 지정할 때만 10분자료 추가 1회 조회")
    args = parser.parse_args()
    from backend.app.config import load_environment
    load_environment()
    secrets = [v for k, v in os.environ.items() if v and (
        k.endswith('_KEY') or any(word in k for word in ('PASSWORD', 'SECRET', 'TOKEN')) or k == 'DATABASE_URL')]
    diag.SECRETS = diag.secret_variants(secrets)
    output = check_water(os.getenv("WATER_LEVEL_API_KEY", "").strip(), args.station_id)
    print(json.dumps(diag.safe(output), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # 예외 원문에 인증 URL이 포함될 수 있으므로 타입만 출력합니다.
        print(json.dumps({"status": "LOCAL_DIAGNOSTIC_ERROR", "type": type(exc).__name__}, ensure_ascii=False))
