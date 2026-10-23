from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..db.session import get_connection
from . import repository, schemas


# ============================================================
# 기본 경로 / 시간대
# ============================================================

ROOT = Path(__file__).resolve().parents[3]

KST = ZoneInfo("Asia/Seoul")


class DemoPreconditionError(RuntimeError):
    """
    Scenario 자체는 정상이나
    Demo 실행에 필요한 준비가 안 된 경우.
    """


# ============================================================
# 시간
# ============================================================


def _now_kst_naive() -> datetime:
    """
    DB TIMESTAMP WITHOUT TIME ZONE에 저장할
    현재 KST 시각.
    """

    return datetime.now(KST).replace(tzinfo=None)


# ============================================================
# Scenario 경로
# ============================================================


def _resolve_scenario_path() -> Path:
    configured_path = os.getenv(
        "OCTV_DEMO_SCENARIO_PATH",
        "demo/scenarios.json",
    )

    path = Path(configured_path)

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


# ============================================================
# Demo 영상 디렉터리
# ============================================================


def _resolve_video_dir() -> Path:
    configured_path = os.getenv(
        "OCTV_DEMO_VIDEO_DIR",
        "demo/videos",
    )

    path = Path(configured_path)

    if not path.is_absolute():
        path = ROOT / path

    return path.resolve()


# ============================================================
# Scenario JSON
# ============================================================


def _load_scenarios() -> dict[str, Any]:
    path = _resolve_scenario_path()

    if not path.exists():
        raise FileNotFoundError(
            f"Demo Scenario 설정 파일을 찾을 수 없습니다. path={path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError("Demo Scenario 설정의 최상위 값은 객체여야 합니다.")

    return payload


def _get_scenario_cases(
    scenario_name: str,
) -> list[dict[str, Any]]:
    scenarios = _load_scenarios()

    scenario = scenarios.get(scenario_name)

    if scenario is None:
        raise LookupError(f"Demo Scenario를 찾을 수 없습니다. scenario={scenario_name}")

    if not isinstance(
        scenario,
        dict,
    ):
        raise RuntimeError("Demo Scenario 설정이 객체가 아닙니다.")

    cases = scenario.get("cases")

    if not isinstance(
        cases,
        list,
    ):
        raise RuntimeError("Demo Scenario의 cases는 배열이어야 합니다.")

    normalized_cases: list[dict[str, Any]] = []

    seen_cctvs: set[tuple[str, str]] = set()

    for index, case in enumerate(
        cases,
        start=1,
    ):
        if not isinstance(
            case,
            dict,
        ):
            raise RuntimeError(f"Demo Scenario case가 객체가 아닙니다. index={index}")

        provider = str(
            case.get(
                "provider",
                "",
            )
        ).strip()

        external_cctv_id = str(
            case.get(
                "external_cctv_id",
                "",
            )
        ).strip()

        if not provider:
            raise RuntimeError(
                f"Demo Scenario case에 provider가 없습니다. index={index}"
            )

        if not external_cctv_id:
            raise RuntimeError(
                f"Demo Scenario case에 external_cctv_id가 없습니다. index={index}"
            )

        key = (
            provider,
            external_cctv_id,
        )

        if key in seen_cctvs:
            raise RuntimeError(
                "같은 CCTV가 Demo Scenario에 "
                "중복 지정되었습니다. "
                f"provider={provider} "
                f"external_cctv_id="
                f"{external_cctv_id}"
            )

        seen_cctvs.add(key)

        normalized_cases.append(case)

    return normalized_cases


# ============================================================
# Demo 영상 검증
# ============================================================


def _validate_demo_video(
    video: str,
) -> str:
    """
    Demo 영상 파일이 실제 존재하는지 확인한다.

    반환값은
    OCTV_DEMO_VIDEO_DIR 기준 상대경로이다.

    DB에는 Windows 절대경로를 저장하지 않는다.
    """

    video = str(video).strip()

    if not video:
        raise DemoPreconditionError("Demo 영상 파일명이 설정되지 않았습니다.")

    raw_path = Path(video)

    if raw_path.is_absolute():
        raise DemoPreconditionError(
            "Demo 영상은 절대경로가 아니라 "
            "OCTV_DEMO_VIDEO_DIR 기준 "
            "상대경로를 사용해야 합니다. "
            f"video={video}"
        )

    video_dir = _resolve_video_dir()

    video_path = (video_dir / raw_path).resolve()

    try:
        relative_path = video_path.relative_to(video_dir)

    except ValueError as exc:
        raise DemoPreconditionError(
            f"Demo 영상 경로가 영상 디렉터리 밖을 가리킵니다. video={video}"
        ) from exc

    if not video_path.exists() or not video_path.is_file():
        raise DemoPreconditionError(
            f"Demo 영상 파일을 찾을 수 없습니다. path={video_path}"
        )

    return relative_path.as_posix()


def get_demo_video_path(
    cctv_id: int,
) -> Path:
    """
    활성화된 Demo CCTV의 실제 영상 파일 경로를 반환한다.
    """

    with get_connection() as connection:
        row = repository.get_demo_cctv_by_id(
            connection,
            cctv_id,
        )

    if row is None:
        raise LookupError(f"Demo CCTV를 찾을 수 없습니다. cctv_id={cctv_id}")

    if not bool(row["is_monitored"]):
        raise DemoPreconditionError(
            f"현재 활성화된 Demo CCTV가 아닙니다. cctv_id={cctv_id}"
        )

    video = str(row["stream_url"] or "").strip()

    if not video:
        raise DemoPreconditionError(
            f"Demo CCTV에 영상이 설정되지 않았습니다. cctv_id={cctv_id}"
        )

    relative_path = _validate_demo_video(video)

    return (_resolve_video_dir() / relative_path).resolve()


# ============================================================
# Demo 상태
# ============================================================


def get_demo_status() -> schemas.DemoStatusResponse:
    scenario_name = "main_demo"

    cases = _get_scenario_cases(scenario_name)

    active_cctv_count = 0

    with get_connection() as connection:
        for case in cases:
            provider = str(case["provider"]).strip()

            external_cctv_id = str(case["external_cctv_id"]).strip()

            expected_video = str(
                case.get(
                    "video",
                    "",
                )
            ).strip()

            row = repository.get_cctv_by_external_id(
                connection,
                provider=provider,
                external_cctv_id=(external_cctv_id),
            )

            if row is None:
                continue

            actual_video = str(row["stream_url"]).strip() if row["stream_url"] else ""

            if bool(row["is_monitored"]) and actual_video == expected_video:
                active_cctv_count += 1

        active_alert_count = repository.count_active_demo_weather_alerts(
            connection,
            scenario_name=(scenario_name),
        )

    active = (
        len(cases) > 0
        and active_cctv_count == len(cases)
        and active_alert_count == len(cases)
    )

    return schemas.DemoStatusResponse(
        enabled=True,
        active=active,
        scenario=(scenario_name if active else None),
        case_count=len(cases),
        active_cctv_count=(active_cctv_count),
        active_alert_count=(active_alert_count),
    )


# ============================================================
# Scenario 조회
# ============================================================


def get_demo_scenario(
    scenario_name: str,
) -> schemas.DemoScenarioResponse:
    cases = _get_scenario_cases(scenario_name)

    return schemas.DemoScenarioResponse(
        scenario=scenario_name,
        case_count=len(cases),
    )


# ============================================================
# Demo 시작
# ============================================================


def start_demo(
    scenario_name: str,
) -> schemas.DemoStartResponse:
    """
    Demo Scenario 실제 시작.

    흐름:

    Scenario 검증
        ↓
    MP4 파일 검증
        ↓
    Demo CCTV DB 존재 검증
        ↓
    Fake 기상특보 ACTIVE 생성
        ↓
    Demo CCTV ALERT 활성화
        ↓
    CCTV Runtime이 DB 변경 감지
        ↓
    MP4 Worker 시작
    """

    cases = _get_scenario_cases(scenario_name)

    prepared_cases: list[dict[str, str]] = []

    # ========================================================
    # 1. Scenario + 영상 + 특보 설정 검증
    # ========================================================

    for case in cases:
        provider = str(case["provider"]).strip()

        external_cctv_id = str(case["external_cctv_id"]).strip()

        if provider.upper() != "DEMO":
            raise DemoPreconditionError(
                f"Demo Scenario에는 DEMO provider만 사용할 수 있습니다. provider={provider}"
            )

        video = _validate_demo_video(
            str(
                case.get(
                    "video",
                    "",
                )
            )
        )

        alert_type = str(
            case.get(
                "alert_type",
                "",
            )
        ).strip()

        alert_level = str(
            case.get(
                "alert_level",
                "",
            )
        ).strip()

        if not alert_type:
            raise DemoPreconditionError(
                f"Demo 특보 종류가 없습니다. external_cctv_id={external_cctv_id}"
            )

        if not alert_level:
            raise DemoPreconditionError(
                f"Demo 특보 단계가 없습니다. external_cctv_id={external_cctv_id}"
            )

        prepared_cases.append(
            {
                "provider": provider,
                "external_cctv_id": external_cctv_id,
                "video": video,
                "alert_type": alert_type,
                "alert_level": alert_level,
            }
        )

    missing_cctvs: list[str] = []

    resolved_rows = []

    # ========================================================
    # 2. 하나의 DB Transaction
    # ========================================================

    with get_connection() as connection:
        # ----------------------------------------------------
        # CCTV 3대 모두 존재하는지 먼저 확인
        # ----------------------------------------------------

        for item in prepared_cases:
            row = repository.get_cctv_by_external_id(
                connection,
                provider=(item["provider"]),
                external_cctv_id=(item["external_cctv_id"]),
            )

            if row is None:
                missing_cctvs.append(f"{item['provider']}/{item['external_cctv_id']}")

                continue

            if row["region_code"] is None:
                raise DemoPreconditionError(
                    "Demo CCTV에 "
                    "region_code가 없습니다. "
                    f"external_cctv_id="
                    f"{item['external_cctv_id']}"
                )

            resolved_rows.append(row)

        if missing_cctvs:
            raise DemoPreconditionError(
                "Demo 실행에 필요한 CCTV가 DB에 없습니다: " + ", ".join(missing_cctvs)
            )

        # ----------------------------------------------------
        # Fake 기상특보 생성
        # ----------------------------------------------------

        issued_at = _now_kst_naive()

        fake_alert_count = 0

        for (
            item,
            cctv_row,
        ) in zip(
            prepared_cases,
            resolved_rows,
            strict=True,
        ):
            external_alert_id = f"DEMO:{scenario_name}:{item['external_cctv_id']}"

            alert_row = repository.upsert_demo_weather_alert(
                connection,
                external_alert_id=(external_alert_id),
                alert_type=(item["alert_type"]),
                alert_level=(item["alert_level"]),
                title=(
                    f"[DEMO] {item['alert_type']} {item['alert_level']} - {cctv_row['name']}"
                ),
                issued_at=(issued_at),
                region_code=str(cctv_row["region_code"]),
            )

            if alert_row is None:
                raise RuntimeError(
                    f"Demo 기상특보 생성에 실패했습니다. external_alert_id={external_alert_id}"
                )

            fake_alert_count += 1

        # ----------------------------------------------------
        # Fake Alert 생성 완료 후
        # Demo CCTV 3대 ALERT 활성화
        # ----------------------------------------------------

        activated_rows = []

        for item in prepared_cases:
            row = repository.activate_demo_cctv(
                connection,
                provider=(item["provider"]),
                external_cctv_id=(item["external_cctv_id"]),
                video=(item["video"]),
            )

            if row is None:
                raise RuntimeError(
                    f"Demo CCTV 활성화에 실패했습니다. external_cctv_id={item['external_cctv_id']}"
                )

            activated_rows.append(row)

    # ========================================================
    # 3. API 응답 구성
    # ========================================================

    cctvs = [
        schemas.DemoResolvedCctv(
            id=int(row["id"]),
            provider=str(row["provider"]),
            external_cctv_id=str(row["external_cctv_id"]),
            name=str(row["name"]),
            region_code=(
                str(row["region_code"]) if row["region_code"] is not None else None
            ),
        )
        for row in activated_rows
    ]

    return schemas.DemoStartResponse(
        scenario=scenario_name,
        ready=True,
        started=True,
        case_count=len(prepared_cases),
        resolved_cctv_count=len(cctvs),
        fake_alert_count=(fake_alert_count),
        cctvs=cctvs,
    )


# ============================================================
# Demo 종료
# ============================================================


def stop_demo(
    scenario_name: str,
) -> schemas.DemoStopResponse:
    """
    Demo Scenario 종료.

    Fake 기상특보:
        ACTIVE → ENDED

    Demo CCTV:
        is_monitored = FALSE
        monitored_mode = OFF
        stream_url = NULL

    실제 UTIC CCTV에는 영향을 주지 않는다.
    """

    cases = _get_scenario_cases(scenario_name)

    stopped_count = 0

    with get_connection() as connection:
        # ----------------------------------------------------
        # Fake 기상특보 종료
        # ----------------------------------------------------

        ended_alert_count = repository.end_demo_weather_alerts(
            connection,
            scenario_name=(scenario_name),
            ended_at=(_now_kst_naive()),
        )

        # ----------------------------------------------------
        # Demo CCTV만 OFF 처리
        # ----------------------------------------------------

        for case in cases:
            provider = str(case["provider"]).strip()

            external_cctv_id = str(case["external_cctv_id"]).strip()

            if provider.upper() != "DEMO":
                raise DemoPreconditionError(
                    f"Demo Scenario에는 DEMO provider만 사용할 수 있습니다. provider={provider}"
                )

            row = repository.deactivate_demo_cctv(
                connection,
                provider=(provider),
                external_cctv_id=(external_cctv_id),
            )

            if row is not None:
                stopped_count += 1

    return schemas.DemoStopResponse(
        scenario=scenario_name,
        stopped=True,
        case_count=len(cases),
        stopped_cctv_count=(stopped_count),
        ended_alert_count=(ended_alert_count),
    )
