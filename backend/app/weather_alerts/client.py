"""기상청 API허브의 현재 기상특보 현황을 조회하고 정규화한다."""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_PATH = ROOT / "backend" / ".env"

KMA_WARNING_STATUS_URL = (
    "https://apihub.kma.go.kr/api/typ01/url/"
    "wrn_now_data_new.php"
)


# ============================================================
# 내부에서 사용하는 정규화 코드
# ============================================================

WARNING_NAMES = {
    "W": "강풍",
    "R": "호우",
    "C": "한파",
    "D": "건조",
    "O": "폭풍해일",
    "N": "지진해일",
    "V": "풍랑",
    "T": "태풍",
    "S": "대설",
    "Y": "황사",
    "H": "폭염",
    "F": "안개",
}


WARNING_CODE_ALIASES = {
    # 코드 형태
    "W": "W",
    "R": "R",
    "C": "C",
    "D": "D",
    "O": "O",
    "N": "N",
    "V": "V",
    "T": "T",
    "S": "S",
    "Y": "Y",
    "H": "H",
    "F": "F",

    # 기상청 한글 표출 형태
    "강풍": "W",
    "호우": "R",
    "한파": "C",
    "건조": "D",
    "해일": "O",
    "폭풍해일": "O",
    "지진해일": "N",
    "풍랑": "V",
    "태풍": "T",
    "대설": "S",
    "황사": "Y",
    "폭염": "H",
    "안개": "F",
}


LEVEL_NAMES = {
    "1": "예비특보",
    "2": "주의보",
    "3": "경보",
}


LEVEL_CODE_ALIASES = {
    "1": "1",
    "2": "2",
    "3": "3",

    "예비": "1",
    "예비특보": "1",

    "주의": "2",
    "주의보": "2",

    "경보": "3",
}


COMMAND_NAMES = {
    "1": "발표",
    "2": "대치",
    "3": "해제",
    "4": "대치해제",
    "5": "연장",
    "6": "변경",
    "7": "변경해제",
}


COMMAND_CODE_ALIASES = {
    "1": "1",
    "2": "2",
    "3": "3",
    "4": "4",
    "5": "5",
    "6": "6",
    "7": "7",

    "발표": "1",
    "대치": "2",
    "해제": "3",
    "대치해제": "4",
    "연장": "5",
    "변경": "6",
    "변경해제": "7",
}


ENDED_COMMAND_CODES = {
    "3",  # 해제
    "4",  # 대치해제
    "7",  # 변경해제
}


@dataclass(frozen=True)
class KmaWarningStatus:
    """기상청 현재 특보현황 한 행."""

    weather_region_code: str
    region_name: str

    issued_at: datetime
    effective_at: datetime | None

    warning_code: str
    warning_name: str

    level_code: str
    level_name: str

    command_code: str
    command_name: str

    active: bool

    @property
    def external_alert_id(self) -> str:
        """
        weather_alerts에서 사용할 외부 특보 식별자.
        """

        issued_key = self.issued_at.strftime(
            "%Y%m%d%H%M"
        )

        return (
            f"KMA:{issued_key}:"
            f"{self.weather_region_code}:"
            f"{self.warning_code}:"
            f"{self.level_code}"
        )

    @property
    def title(self) -> str:
        return (
            f"{self.warning_name} "
            f"{self.level_name}"
        )


def _load_kma_api_key() -> str:
    """
    환경변수 또는 backend/.env에서
    KMA_API_KEY를 읽는다.
    """

    values = dotenv_values(
        BACKEND_ENV_PATH,
        interpolate=False,
    )

    key = os.environ.get(
        "KMA_API_KEY",
        values.get(
            "KMA_API_KEY"
        ),
    )

    if (
        not key
        or not key.strip()
    ):
        raise ValueError(
            "backend/.env에 "
            "KMA_API_KEY를 설정해야 합니다."
        )

    return key.strip()


def _decode_response(
    content: bytes,
) -> str:
    """
    기상청 text 응답을
    일반적인 한글 인코딩 후보로 해석한다.
    """

    for encoding in (
        "utf-8-sig",
        "cp949",
        "euc-kr",
    ):
        try:
            return content.decode(
                encoding
            )

        except UnicodeDecodeError:
            continue

    raise RuntimeError(
        "기상특보 응답 문자 인코딩을 "
        "해석할 수 없습니다."
    )


def _parse_kst_naive(
    value: str,
) -> datetime | None:
    """
    YYYYMMDDHHMM KST 문자열을
    naive datetime으로 변환한다.
    """

    text = value.strip()

    if (
        not text
        or text in {
            "-",
            "0",
        }
    ):
        return None

    if (
        len(text) < 12
        or not text[:12].isdigit()
    ):
        raise ValueError(
            "기상특보 시각 형식이 "
            "올바르지 않습니다: "
            f"{value!r}"
        )

    return datetime.strptime(
        text[:12],
        "%Y%m%d%H%M",
    )


def _split_data_row(
    line: str,
) -> list[str]:
    """
    쉼표 구분 응답과
    공백 구분 응답을 모두 처리한다.
    """

    if "," in line:
        return [
            value.strip()
            for value in next(
                csv.reader(
                    [line],
                    skipinitialspace=True,
                )
            )
        ]

    return line.split()


def _normalize_warning_code(
    value: str,
) -> str:
    """
    WRN 값이 코드 또는 한글명 어느 형태로 와도
    내부 코드로 변환한다.

    예:
        W    -> W
        강풍 -> W
        S    -> S
        대설 -> S
    """

    text = value.strip()

    code = (
        WARNING_CODE_ALIASES.get(
            text
        )
    )

    if code is None:
        raise RuntimeError(
            "알 수 없는 기상특보 종류입니다: "
            f"{text!r}"
        )

    return code


def _normalize_level_code(
    value: str,
) -> str:
    """
    LVL 값을 내부 코드로 변환한다.

    예:
        1 / 예비 / 예비특보 -> 1
        2 / 주의 / 주의보   -> 2
        3 / 경보            -> 3
    """

    text = value.strip()

    code = (
        LEVEL_CODE_ALIASES.get(
            text
        )
    )

    if code is None:
        raise RuntimeError(
            "알 수 없는 기상특보 수준입니다: "
            f"{text!r}"
        )

    return code


def _normalize_command_code(
    value: str,
) -> str:
    """
    CMD 값을 내부 코드로 변환한다.

    코드 또는 한글 특보명령을 모두 지원한다.
    """

    text = value.strip()

    code = (
        COMMAND_CODE_ALIASES.get(
            text
        )
    )

    if code is None:
        raise RuntimeError(
            "알 수 없는 기상특보 명령입니다: "
            f"{text!r}"
        )

    return code


def parse_current_warnings(
    text: str,
) -> list[KmaWarningStatus]:
    """
    wrn_now_data_new.php 응답을 파싱한다.

    컬럼:

    REG_UP
    REG_UP_KO
    REG_ID
    REG_KO
    TM_FC
    TM_EF
    WRN
    LVL
    CMD

    WRN / LVL / CMD는
    API 출력형식에 따라 코드 또는 한글 문자열로
    들어올 수 있으므로 내부 코드로 정규화한다.
    """

    stripped = text.strip()
    lowered = stripped.lower()

    if (
        "<html" in lowered
        or "<!doctype" in lowered
    ):
        raise RuntimeError(
            "기상특보 API가 "
            "HTML 오류 응답을 반환했습니다."
        )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    comment_seen = any(
        line.startswith("#")
        for line in lines
    )

    data_lines = [
        line
        for line in lines
        if not line.startswith("#")
    ]

    if not data_lines:
        if comment_seen:
            return []

        raise RuntimeError(
            "기상특보 API 응답 형식을 "
            "확인할 수 없습니다."
        )

    result: list[
        KmaWarningStatus
    ] = []

    for line in data_lines:
        row = _split_data_row(
            line
        )

        if len(row) < 9:
            raise RuntimeError(
                "기상특보 API 행의 "
                "컬럼 수가 예상보다 적습니다."
            )

        (
            _region_parent,
            _region_parent_name,
            weather_region_code,
            region_name,
            tm_fc,
            tm_ef,
            raw_warning,
            raw_level,
            raw_command,
        ) = row[:9]

        issued_at = (
            _parse_kst_naive(
                tm_fc
            )
        )

        if issued_at is None:
            raise RuntimeError(
                "현재 기상특보 행에 "
                "발표시각(TM_FC)이 없습니다."
            )

        warning_code = (
            _normalize_warning_code(
                raw_warning
            )
        )

        level_code = (
            _normalize_level_code(
                raw_level
            )
        )

        command_code = (
            _normalize_command_code(
                raw_command
            )
        )

        result.append(
            KmaWarningStatus(
                weather_region_code=(
                    weather_region_code
                ),
                region_name=(
                    region_name
                ),
                issued_at=(
                    issued_at
                ),
                effective_at=(
                    _parse_kst_naive(
                        tm_ef
                    )
                ),
                warning_code=(
                    warning_code
                ),
                warning_name=(
                    WARNING_NAMES[
                        warning_code
                    ]
                ),
                level_code=(
                    level_code
                ),
                level_name=(
                    LEVEL_NAMES[
                        level_code
                    ]
                ),
                command_code=(
                    command_code
                ),
                command_name=(
                    COMMAND_NAMES[
                        command_code
                    ]
                ),
                active=(
                    command_code
                    not in
                    ENDED_COMMAND_CODES
                ),
            )
        )

    return result


def fetch_current_warnings(
    timeout_sec: float = 30.0,
    max_retries: int = 3,
) -> list[KmaWarningStatus]:
    """
    기상청 API허브에서
    현재 특보현황을 조회한다.

    일시적인 Timeout / 연결 오류는
    재시도한다.

    API Key가 URL에 포함될 수 있으므로
    requests 예외 원문은 외부로 노출하지 않는다.
    """

    if timeout_sec <= 0:
        raise ValueError(
            "timeout_sec은 "
            "0보다 커야 합니다."
        )

    if max_retries < 1:
        raise ValueError(
            "max_retries는 "
            "1 이상이어야 합니다."
        )

    last_error_type = None

    for attempt in range(
        1,
        max_retries + 1,
    ):
        try:
            response = requests.get(
                KMA_WARNING_STATUS_URL,
                params={
                    "fe": "f",
                    "tm": "",
                    "disp": "0",
                    "help": "0",
                    "authKey":
                        _load_kma_api_key(),
                },
                timeout=(
                    10,
                    timeout_sec,
                ),
            )

            # 인증 오류는 재시도해도
            # 해결되지 않으므로 즉시 실패.
            if response.status_code in {
                401,
                403,
            }:
                raise RuntimeError(
                    "기상청 특보현황 API 접근이 "
                    "거부되었습니다. "
                    "API 활용신청/승인 상태와 "
                    "인증키 권한을 확인하세요."
                )

            response.raise_for_status()

            return parse_current_warnings(
                _decode_response(
                    response.content
                )
            )

        except RuntimeError:
            # 위에서 의도적으로 생성한
            # 인증/파싱 오류는 재시도하지 않는다.
            raise

        except (
            requests.Timeout,
            requests.ConnectionError,
        ) as exc:
            last_error_type = (
                type(exc).__name__
            )

        except requests.HTTPError as exc:
            # 5xx는 일시적인 서버 문제일 수 있으므로
            # 재시도한다.
            status_code = (
                exc.response.status_code
                if exc.response
                is not None
                else None
            )

            if (
                status_code is None
                or status_code < 500
            ):
                raise RuntimeError(
                    "기상청 특보현황 API "
                    "요청에 실패했습니다."
                ) from None

            last_error_type = (
                f"HTTP_{status_code}"
            )

        except requests.RequestException as exc:
            last_error_type = (
                type(exc).__name__
            )

        if attempt >= max_retries:
            break

        wait_seconds = (
            attempt * 2
        )

        print(
            "[KMA WARNING API] "
            f"조회 실패 "
            f"({attempt}/{max_retries}) "
            f"/ {last_error_type} "
            f"→ {wait_seconds}초 후 재시도"
        )

        time.sleep(
            wait_seconds
        )

    raise RuntimeError(
        "기상청 특보현황 API 조회에 "
        f"{max_retries}회 연속 실패했습니다. "
        f"마지막 오류: {last_error_type}"
    )