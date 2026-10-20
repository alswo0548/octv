from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any, Mapping


# ============================================================
# Context Source 이름
# ============================================================

CONTEXT_SOURCE_NAMES = (
    "weather",
    "water_level",
    "traffic",
)


# ============================================================
# 좌표 검증
# ============================================================

def _coordinate(
    incident: Mapping[str, Any],
    name: str,
    minimum: float,
    maximum: float,
) -> float:
    """
    Incident에 저장된 위도/경도를 검증하고
    float 값으로 반환한다.
    """

    raw = incident.get(name)

    if isinstance(raw, bool):
        raise ValueError(
            f"{name} 좌표를 확인하세요."
        )

    try:
        value = float(raw)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        raise ValueError(
            f"{name} 좌표를 확인하세요."
        ) from None

    if (
        not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(
            f"{name} 좌표 범위를 확인하세요."
        )

    return value


# ============================================================
# 사건 위치
# ============================================================

def resolve_incident_location(
    incident: Mapping[str, Any],
) -> dict[str, Any]:
    """
    사건이 발생한 CCTV의 위치 정보를 반환한다.

    Context 조회 기준은 CCTV ID가 아니라
    사건에 저장된 위도/경도/지역코드다.
    """

    if not isinstance(incident, Mapping):
        raise ValueError(
            "사건 정보는 객체여야 합니다."
        )

    latitude = _coordinate(
        incident,
        "latitude",
        -90.0,
        90.0,
    )

    longitude = _coordinate(
        incident,
        "longitude",
        -180.0,
        180.0,
    )

    region_code = str(
        incident.get("region_code") or ""
    ).strip()

    return {
        "latitude": latitude,
        "longitude": longitude,
        "region_code": region_code,
    }


# ============================================================
# Context Source 설정
# ============================================================

def resolve_context_sources(
    settings: Mapping[str, Any],
    incident: Mapping[str, Any],
) -> dict[str, Any]:
    """
    사건 위치를 기준으로 사용할 Context 설정을 준비한다.

    기존 방식:
        CCTV ID
        → runtime_config의 cctvs[id]
        → 수동 설정

    변경 방식:
        사건 위치
        → latitude / longitude / region_code
        → 공통 Context Source 설정
        → 각 Provider Resolver

    실제 기상 관측점, 수위 관측소,
    도로/교통 구간 자동 탐색은
    각 외부 API 제공기관이 확정된 뒤
    이 Resolver 계층에서 처리한다.
    """

    if not isinstance(settings, Mapping):
        raise ValueError(
            "실행 설정은 객체여야 합니다."
        )

    location = resolve_incident_location(
        incident
    )

    # --------------------------------------------------------
    # 기존 CCTV ID별 수동 mapping 방지
    # --------------------------------------------------------

    legacy_cctvs = settings.get("cctvs")

    if (
        legacy_cctvs is not None
        and legacy_cctvs != {}
    ):
        raise ValueError(
            "CCTV ID별 수동 Context mapping은 "
            "지원하지 않습니다. "
            "사건 위치 기반 Context 설정을 사용하세요."
        )

    # --------------------------------------------------------
    # Provider 공통 설정
    # --------------------------------------------------------

    sources = deepcopy(
        settings.get(
            "context_sources",
            {},
        )
    )

    if not isinstance(sources, dict):
        raise ValueError(
            "context_sources 설정은 "
            "JSON 객체여야 합니다."
        )

    weather = deepcopy(
        sources.get(
            "weather",
            {
                "mapped": False,
            },
        )
    )

    water_level = deepcopy(
        sources.get(
            "water_level",
            {
                "mapped": False,
            },
        )
    )

    traffic = deepcopy(
        sources.get(
            "traffic",
            {},
        )
    )

    for name, source in (
        ("weather", weather),
        ("water_level", water_level),
        ("traffic", traffic),
    ):
        if not isinstance(source, dict):
            raise ValueError(
                f"context_sources.{name} 설정은 "
                "JSON 객체여야 합니다."
            )

    return {
        "location": location,
        "weather": weather,
        "water_level": water_level,
        "traffic": traffic,
    }