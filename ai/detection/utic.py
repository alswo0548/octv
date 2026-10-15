from __future__ import annotations

import os
from pathlib import Path

import requests
from dotenv import load_dotenv


# =========================================================
# 기본 경로
# =========================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

BACKEND_ENV_PATH = (
    ROOT
    / "backend"
    / ".env"
)


# =========================================================
# UTIC URL
# =========================================================

UTIC_BASE_URL = (
    "https://www.utic.go.kr"
)

UTIC_OPEN_DATA_URL = (
    f"{UTIC_BASE_URL}"
    "/guide/cctvOpenData.do"
)

UTIC_CCTV_INFO_URL = (
    f"{UTIC_BASE_URL}"
    "/map/getCctvInfoById.do"
)


# =========================================================
# UTIC 인증키
# =========================================================


def load_utic_key() -> str:
    """
    backend/.env에서 UTIC CCTV 인증키를 읽는다.

    FastAPI / CCTV Runtime / 테스트 여부와 관계없이
    동일한 UTIC 인증 설정을 사용한다.
    """

    load_dotenv(
        dotenv_path=(
            BACKEND_ENV_PATH
        )
    )

    key = os.getenv(
        "UTIC_CCTV_KEY"
    )

    if not key:

        raise RuntimeError(
            "backend/.env에 "
            "UTIC_CCTV_KEY가 없습니다."
        )

    return key


# =========================================================
# UTIC Stream URL 조회
# =========================================================


def get_utic_stream_url(
    external_cctv_id: str,
) -> tuple[str, dict]:
    """
    UTIC external_cctv_id로 CCTV 정보를 조회하고
    실제 영상 Stream URL을 반환한다.

    CaptureWorker의 최초 연결 및 재연결 시
    호출할 수 있다.
    """

    key = load_utic_key()

    with requests.Session() as session:

        page_response = session.get(
            UTIC_OPEN_DATA_URL,
            params={
                "key":
                    key,
            },
            timeout=20,
        )

        page_response.raise_for_status()

        info_response = session.get(
            UTIC_CCTV_INFO_URL,
            params={
                "cctvId":
                    external_cctv_id,
            },
            headers={
                "Referer":
                    page_response.url,

                "X-Requested-With":
                    "XMLHttpRequest",
            },
            timeout=20,
        )

        info_response.raise_for_status()

        data = (
            info_response.json()
        )

    stream_id = (
        data.get(
            "ID"
        )
    )

    if not stream_id:

        raise RuntimeError(
            "UTIC CCTV Stream ID가 "
            "없습니다. "
            f"external_cctv_id="
            f"{external_cctv_id}"
        )

    stream_url = (
        "https://cctvsec.ktict.co.kr/"
        + stream_id
    )

    return (
        stream_url,
        data,
    )
