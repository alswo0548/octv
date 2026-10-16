"""CCTV WebRTC 스트리밍을 위한 MediaMTX 연동."""

from __future__ import annotations

import hashlib
import os
import socket
import ssl
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests
from dotenv import load_dotenv

from ai.detection.utic import (
    get_utic_stream_url,
)


# ============================================================
# 환경 설정
# ============================================================

ROOT = (
    Path(__file__)
    .resolve()
    .parents[3]
)

BACKEND_ENV_PATH = (
    ROOT
    / "backend"
    / ".env"
)

load_dotenv(
    dotenv_path=BACKEND_ENV_PATH
)


MEDIAMTX_API_URL = (
    os.getenv(
        "MEDIAMTX_API_URL",
        "http://127.0.0.1:9997",
    )
    .rstrip("/")
)

MEDIAMTX_WEBRTC_BASE_URL = (
    os.getenv(
        "MEDIAMTX_WEBRTC_BASE_URL",
        "http://127.0.0.1:8889",
    )
    .rstrip("/")
)

MEDIAMTX_REQUEST_TIMEOUT_SEC = 10

SOURCE_ON_DEMAND_START_TIMEOUT = "15s"
SOURCE_ON_DEMAND_CLOSE_AFTER = "10s"


# ============================================================
# Stream source 변환
# ============================================================


def _convert_rtmp_for_mediamtx(
    stream_url: str,
) -> str:
    """
    OpenCV / FFmpeg용 RTMP URL을
    MediaMTX source 형식으로 변환한다.

    예:
        rtmp://host:1935/live/207.stream

    MediaMTX:
        rtmp://host:1935/live#207.stream
    """

    if "/" not in stream_url:
        raise ValueError(
            "RTMP Stream URL 형식이 "
            "올바르지 않습니다."
        )

    base_url, stream_key = (
        stream_url.rsplit(
            "/",
            1,
        )
    )

    if not stream_key:
        raise ValueError(
            "RTMP Stream Key가 없습니다."
        )

    return (
        f"{base_url}"
        f"#{stream_key}"
    )


def _get_https_certificate_fingerprint(
    stream_url: str,
) -> str:
    """
    HTTPS source 서버 인증서의
    SHA-256 fingerprint를 반환한다.

    UTIC HLS 서버 인증서가
    MediaMTX 컨테이너의 기본 CA 저장소에서
    검증되지 않는 경우 sourceFingerprint로 사용한다.
    """

    parsed = urlsplit(
        stream_url
    )

    if parsed.scheme.lower() != "https":
        raise ValueError(
            "HTTPS URL만 인증서 fingerprint를 "
            "조회할 수 있습니다."
        )

    hostname = parsed.hostname

    if not hostname:
        raise ValueError(
            "Stream URL에서 hostname을 "
            "확인할 수 없습니다."
        )

    port = (
        parsed.port
        or 443
    )

    context = (
        ssl.create_default_context()
    )

    # fingerprint를 직접 검증값으로 사용할 것이므로
    # 이 연결 자체에서는 CA 검증을 수행하지 않는다.
    context.check_hostname = False
    context.verify_mode = (
        ssl.CERT_NONE
    )

    with socket.create_connection(
        (
            hostname,
            port,
        ),
        timeout=(
            MEDIAMTX_REQUEST_TIMEOUT_SEC
        ),
    ) as raw_socket:

        with context.wrap_socket(
            raw_socket,
            server_hostname=hostname,
        ) as tls_socket:

            certificate = (
                tls_socket.getpeercert(
                    binary_form=True
                )
            )

    if not certificate:
        raise RuntimeError(
            "HTTPS source 인증서를 "
            "가져오지 못했습니다."
        )

    return hashlib.sha256(
        certificate
    ).hexdigest()


def _build_mediamtx_source(
    stream_url: str,
) -> tuple[
    str,
    str,
]:
    """
    UTIC Stream URL을 MediaMTX에서 사용할
    source URL과 fingerprint로 변환한다.

    반환:
        (
            source_url,
            source_fingerprint,
        )
    """

    scheme = (
        urlsplit(
            stream_url
        )
        .scheme
        .lower()
    )

    # --------------------------------------------------------
    # 서울교통정보센터 RTMP
    # --------------------------------------------------------

    if scheme in {
        "rtmp",
        "rtmps",
    }:

        return (
            _convert_rtmp_for_mediamtx(
                stream_url
            ),
            "",
        )

    # --------------------------------------------------------
    # UTIC HTTPS HLS
    # --------------------------------------------------------

    if scheme == "https":

        fingerprint = (
            _get_https_certificate_fingerprint(
                stream_url
            )
        )

        return (
            stream_url,
            fingerprint,
        )

    # --------------------------------------------------------
    # 기타 HTTP source
    # --------------------------------------------------------

    if scheme == "http":

        return (
            stream_url,
            "",
        )

    raise ValueError(
        "지원하지 않는 CCTV Stream "
        f"프로토콜입니다: {scheme}"
    )


# ============================================================
# MediaMTX Control API
# ============================================================


def _path_name(
    cctv_id: int,
) -> str:

    return (
        f"cctv-{cctv_id}"
    )


def _config_path_url(
    operation: str,
    path_name: str,
) -> str:

    encoded_name = quote(
        path_name,
        safe="",
    )

    return (
        f"{MEDIAMTX_API_URL}"
        "/v3/config/paths/"
        f"{operation}/"
        f"{encoded_name}"
    )


def _upsert_mediamtx_path(
    path_name: str,
    source_url: str,
    source_fingerprint: str,
) -> None:
    """
    MediaMTX path가 이미 있으면 PATCH,
    없으면 ADD한다.
    """

    payload = {
        "source":
            source_url,

        "sourceOnDemand":
            True,

        "sourceOnDemandStartTimeout":
            SOURCE_ON_DEMAND_START_TIMEOUT,

        "sourceOnDemandCloseAfter":
            SOURCE_ON_DEMAND_CLOSE_AFTER,

        "sourceFingerprint":
            source_fingerprint,
    }

    # --------------------------------------------------------
    # 기존 path 갱신 시도
    # --------------------------------------------------------

    patch_response = requests.patch(
        _config_path_url(
            "patch",
            path_name,
        ),
        json=payload,
        timeout=(
            MEDIAMTX_REQUEST_TIMEOUT_SEC
        ),
    )

    if patch_response.status_code == 200:
        return

    # --------------------------------------------------------
    # 없는 path이면 신규 생성
    # --------------------------------------------------------

    if patch_response.status_code == 404:

        add_response = requests.post(
            _config_path_url(
                "add",
                path_name,
            ),
            json=payload,
            timeout=(
                MEDIAMTX_REQUEST_TIMEOUT_SEC
            ),
        )

        if add_response.status_code == 200:
            return

        raise RuntimeError(
            "MediaMTX path 생성에 실패했습니다. "
            f"status={add_response.status_code}"
        )

    raise RuntimeError(
        "MediaMTX path 갱신에 실패했습니다. "
        f"status={patch_response.status_code}"
    )


def remove_cctv_stream(
    cctv_id: int,
) -> None:
    """
    CCTV 감시가 OFF가 될 때
    MediaMTX path를 제거한다.

    MediaMTX가 내려가 있거나 path가 없어도
    CCTV 감시 상태 변경 자체는 실패시키지 않는다.
    """

    path_name = _path_name(
        cctv_id
    )

    try:

        response = requests.delete(
            _config_path_url(
                "delete",
                path_name,
            ),
            timeout=(
                MEDIAMTX_REQUEST_TIMEOUT_SEC
            ),
        )

        if response.status_code in {
            200,
            404,
        }:
            return

        print(
            "[CCTV STREAM WARNING] "
            "MediaMTX path 삭제 실패 "
            f"/ cctv_id={cctv_id} "
            f"/ status={response.status_code}"
        )

    except requests.RequestException as exc:

        print(
            "[CCTV STREAM WARNING] "
            "MediaMTX path 삭제 요청 실패 "
            f"/ cctv_id={cctv_id} "
            f"/ error={exc}"
        )


# ============================================================
# CCTV Stream 준비
# ============================================================


def prepare_cctv_stream(
    cctv_id: int,
    external_cctv_id: str,
) -> dict:
    """
    최신 UTIC Stream URL을 조회하고
    MediaMTX path를 생성 또는 갱신한다.

    실제 영상 source URL은 API 응답으로 노출하지 않는다.
    """

    (
        stream_url,
        _,
    ) = get_utic_stream_url(
        external_cctv_id
    )

    (
        source_url,
        source_fingerprint,
    ) = _build_mediamtx_source(
        stream_url
    )

    path_name = _path_name(
        cctv_id
    )

    _upsert_mediamtx_path(
        path_name=path_name,
        source_url=source_url,
        source_fingerprint=(
            source_fingerprint
        ),
    )

    playback_url = (
        f"{MEDIAMTX_WEBRTC_BASE_URL}"
        f"/{path_name}"
    )

    whep_url = (
        f"{playback_url}"
        "/whep"
    )

    return {
        "cctv_id":
            cctv_id,

        "path":
            path_name,

        "playback_url":
            playback_url,

        "whep_url":
            whep_url,
    }