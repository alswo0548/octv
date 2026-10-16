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
# UTIC CCTV 정보 조회
# =========================================================


def get_utic_cctv_info(
    external_cctv_id: str,
) -> dict:
    """
    UTIC external_cctv_id로 CCTV 정보를 조회한다.

    기관별 CCTV는 실제 영상 제공 방식이 다를 수 있으므로
    여기서는 원본 CCTV 정보만 조회하고,
    실제 Stream URL 생성은 별도 함수에서 처리한다.
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

    if not isinstance(
        data,
        dict,
    ):

        raise RuntimeError(
            "UTIC CCTV 정보 응답 형식이 "
            "올바르지 않습니다. "
            f"external_cctv_id="
            f"{external_cctv_id}"
        )

    return data


# =========================================================
# 기관별 Stream URL 생성
# =========================================================


def _build_seoul_stream_url(
    external_cctv_id: str,
    data: dict,
) -> str:
    """
    서울교통정보센터 CCTV(L01...) Stream URL을 생성한다.

    UTIC의 CCTV 재생 스크립트 기준:

    streamer:
        rtmp://210.179.218.{CH}:1935/live

    file:
        {ID}.stream
    """

    stream_id = data.get(
        "ID"
    )

    channel = data.get(
        "CH"
    )

    if stream_id in {
        None,
        "",
    }:

        raise RuntimeError(
            "서울 CCTV Stream ID가 없습니다. "
            f"external_cctv_id="
            f"{external_cctv_id}"
        )

    if channel in {
        None,
        "",
    }:

        raise RuntimeError(
            "서울 CCTV CH 정보가 없습니다. "
            f"external_cctv_id="
            f"{external_cctv_id}"
        )

    return (
        "rtmp://210.179.218."
        f"{channel}"
        ":1935/live/"
        f"{stream_id}"
        ".stream"
    )


def _build_default_stream_url(
    external_cctv_id: str,
    data: dict,
) -> str:
    """
    기존 UTIC HLS 계열 Stream URL을 생성한다.

    현재 국가교통정보센터 고속도로 CCTV 등에서
    UTIC 응답의 ID가 실제 KTICT Stream 경로로 사용된다.
    """

    stream_id = data.get(
        "ID"
    )

    if not stream_id:

        raise RuntimeError(
            "UTIC CCTV Stream ID가 "
            "없습니다. "
            f"external_cctv_id="
            f"{external_cctv_id}"
        )

    return (
        "https://cctvsec.ktict.co.kr/"
        + str(
            stream_id
        )
    )


# =========================================================
# UTIC Stream URL 조회
# =========================================================


def get_utic_stream_url(
    external_cctv_id: str,
) -> tuple[str, dict]:
    """
    UTIC external_cctv_id로 CCTV 정보를 조회하고
    기관 유형에 맞는 실제 영상 Stream URL을 반환한다.

    지원 방식:

    1. 서울교통정보센터 CCTV
       external_cctv_id가 L01...인 경우
       RTMP Stream을 생성한다.

    2. 기존 UTIC HLS 계열
       UTIC 응답의 ID를 KTICT Stream 경로로 사용한다.

    CaptureWorker의 최초 연결 및 재연결 시
    호출할 수 있다.
    """

    data = get_utic_cctv_info(
        external_cctv_id
    )

    # -----------------------------------------------------
    # 서울교통정보센터
    # -----------------------------------------------------

    if external_cctv_id.upper().startswith(
        "L01"
    ):

        stream_url = (
            _build_seoul_stream_url(
                external_cctv_id,
                data,
            )
        )

    # -----------------------------------------------------
    # 기존 UTIC / 고속도로 HLS 계열
    # -----------------------------------------------------

    else:

        stream_url = (
            _build_default_stream_url(
                external_cctv_id,
                data,
            )
        )

    return (
        stream_url,
        data,
    )