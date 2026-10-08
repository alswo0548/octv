from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
BACKEND_ENV = ROOT / "backend" / ".env"


# 실행 순서가 중요함
# region을 먼저 적재해야 다른 데이터들이 region_code를 참조할 수 있음
SYNC_STEPS = [
    ("지역정보", "load_regions.py"),
    ("기상특보 지역코드", "load_weather_region_codes.py"),
    ("소방기관", "load_fire_agencies.py"),
    ("경찰기관", "load_police_agencies.py"),
    ("경기도 지자체", "load_local_government_agencies.py"),
    ("서울특별시 지자체", "load_seoul_local_government_agencies.py"),
    ("서울 도로관리기관", "load_road_management_agencies.py"),
    ("경기도 도로관리기관", "load_gyeonggi_road_management_agencies.py"),
]


# 각 loader 실행에 필요한 API KEY
REQUIRED_API_KEYS = [
    "DATA_GO_KR_SERVICE_KEY",
    "KMA_API_KEY",
    "SAFETY_DATA_SERVICE_KEY",
    "GYEONGGI_DATA_KEY",
    "SAFETY_DATA_COMMON_POI_KEY",
    "SEOUL_OPENAPI_KEY",
    "KAKAO_REST_API_KEY",
]


# Git에 같이 포함할 기준정보 원본 파일
REQUIRED_REFERENCE_FILES = [
    ROOT
    / "database"
    / "reference"
    / "fire"
    / "소방청_시도 소방서 현황_20260701.csv",

    ROOT
    / "database"
    / "reference"
    / "fire"
    / "소방서 안전센터 구조대 위치정보_2025.xlsx",

    ROOT
    / "database"
    / "reference"
    / "fire"
    / "경기도소방서현황및관할구역현황.csv",

    ROOT
    / "database"
    / "reference"
    / "road_management"
    / "seoul"
    / "TL_BSBND_A.zip",

    ROOT
    / "database"
    / "reference"
    / "road_management"
    / "seoul"
    / "서울시 상권분석서비스(영역-자치구).zip",
]


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def validate_environment() -> None:
    """
    동기화 실행 전에 필요한 파일과 환경변수가 준비되어 있는지 확인한다.
    """

    print_section("[PRECHECK] 실행 환경 확인")

    if not BACKEND_ENV.exists():
        raise FileNotFoundError(
            "backend/.env 파일이 없습니다. "
            "backend/.env.example을 참고해 생성하세요."
        )

    env = dotenv_values(
        BACKEND_ENV,
        interpolate=False,
    )

    missing_keys = [
        key
        for key in REQUIRED_API_KEYS
        if not str(env.get(key) or "").strip()
    ]

    if missing_keys:
        raise RuntimeError(
            "backend/.env에 필요한 API KEY가 없습니다: "
            + ", ".join(missing_keys)
        )

    missing_scripts = [
        filename
        for _, filename in SYNC_STEPS
        if not (SCRIPTS_DIR / filename).exists()
    ]

    if missing_scripts:
        raise FileNotFoundError(
            "실행 파일을 찾을 수 없습니다: "
            + ", ".join(missing_scripts)
        )

    missing_files = [
        path
        for path in REQUIRED_REFERENCE_FILES
        if not path.exists()
    ]

    if missing_files:
        relative_paths = [
            str(path.relative_to(ROOT))
            for path in missing_files
        ]

        raise FileNotFoundError(
            "기준정보 원본 파일을 찾을 수 없습니다: "
            + ", ".join(relative_paths)
        )

    print("PASS: backend/.env API KEY 확인")
    print("PASS: load_*.py 실행 파일 확인")
    print("PASS: 기준정보 원본 파일 확인")


def run_step(
    index: int,
    total: int,
    label: str,
    filename: str,
) -> None:
    """
    각 load_*.py 파일을 Python 모듈로 실행한다.
    하나라도 실패하면 전체 sync를 중단한다.
    """

    script_path = SCRIPTS_DIR / filename

    print_section(
        f"[{index}/{total}] {label} 동기화"
    )

    print(f"실행: {filename}")

    if not script_path.exists():
        raise FileNotFoundError(
            f"실행 파일을 찾을 수 없습니다: {script_path}"
        )

    module_name = (
        "scripts."
        + script_path.stem
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            module_name,
        ],
        cwd=ROOT,
        check=True,
    )

    print()
    print(f"PASS: {label}")


def main() -> int:
    print_section("OCTV REFERENCE DATA SYNC")

    print(
        "이 스크립트는 기준정보의 최초 적재와 "
        "수동 갱신에 공통으로 사용합니다."
    )

    try:
        validate_environment()

        total = len(SYNC_STEPS)

        for index, (label, filename) in enumerate(
            SYNC_STEPS,
            start=1,
        ):
            run_step(
                index=index,
                total=total,
                label=label,
                filename=filename,
            )

    except subprocess.CalledProcessError as exc:
        print_section("REFERENCE DATA SYNC: FAIL")

        failed_script = Path(
            str(exc.cmd[-1])
        ).name

        print(
            f"실패한 작업: {failed_script}"
        )

        print(
            f"종료 코드: {exc.returncode}"
        )

        print(
            "오류 원인을 수정한 뒤 "
            "동일 명령으로 다시 실행하세요."
        )

        return 1

    except (
        FileNotFoundError,
        RuntimeError,
        OSError,
    ) as exc:
        print_section("REFERENCE DATA SYNC: FAIL")

        print(exc)

        return 1

    print_section("REFERENCE DATA SYNC: PASS")

    print(
        "모든 기준정보 동기화가 완료되었습니다."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())