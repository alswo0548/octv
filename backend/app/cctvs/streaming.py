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

ROOT = Path(__file__).resolve().parents[3]

BACKEND_ENV_PATH = ROOT / "backend" / ".env"

load_dotenv(dotenv_path=BACKEND_ENV_PATH)


MEDIAMTX_API_URL = os.getenv(
    "MEDIAMTX_API_URL",
    "http://127.0.0.1:9997",
).rstrip("/")

MEDIAMTX_WEBRTC_BASE_URL = os.getenv(
    "MEDIAMTX_WEBRTC_BASE_URL",
    "http://127.0.0.1:8889",
).rstrip("/")

MEDIAMTX_REQUEST_TIMEOUT_SEC = 10

SOURCE_ON_DEMAND_START_TIMEOUT = "15s"
SOURCE_ON_DEMAND_CLOSE_AFTER = "60s"


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
        raise ValueError("RTMP Stream URL 형식이 올바르지 않습니다.")

    base_url, stream_key = stream_url.rsplit(
        "/",
        1,
    )

    if not stream_key:
        raise ValueError("RTMP Stream Key가 없습니다.")

    return f"{base_url}#{stream_key}"


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

    parsed = urlsplit(stream_url)

    if parsed.scheme.lower() != "https":
        raise ValueError("HTTPS URL만 인증서 fingerprint를 조회할 수 있습니다.")

    hostname = parsed.hostname

    if not hostname:
        raise ValueError("Stream URL에서 hostname을 확인할 수 없습니다.")

    port = parsed.port or 443

    context = ssl.create_default_context()

    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with socket.create_connection(
        (
            hostname,
            port,
        ),
        timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
    ) as raw_socket:
        with context.wrap_socket(
            raw_socket,
            server_hostname=hostname,
        ) as tls_socket:
            certificate = tls_socket.getpeercert(binary_form=True)

    if not certificate:
        raise RuntimeError("HTTPS source 인증서를 가져오지 못했습니다.")

    return hashlib.sha256(certificate).hexdigest()


def _build_mediamtx_source(
    stream_url: str,
) -> tuple[
    str,
    str,
]:
    """
    UTIC Stream URL을 MediaMTX에서 사용할
    source URL과 fingerprint로 변환한다.
    """

    scheme = urlsplit(stream_url).scheme.lower()

    # 서울교통정보센터 RTMP
    if scheme in {
        "rtmp",
        "rtmps",
    }:
        return (
            _convert_rtmp_for_mediamtx(stream_url),
            "",
        )

    # UTIC HTTPS HLS
    if scheme == "https":
        fingerprint = _get_https_certificate_fingerprint(stream_url)

        return (
            stream_url,
            fingerprint,
        )

    # 기타 HTTP
    if scheme == "http":
        return (
            stream_url,
            "",
        )

    raise ValueError(f"지원하지 않는 CCTV Stream 프로토콜입니다: {scheme}")


# ============================================================
# MediaMTX URL
# ============================================================


def _path_name(
    cctv_id: int,
) -> str:

    return f"cctv-{cctv_id}"


def _config_path_url(
    operation: str,
    path_name: str,
) -> str:

    encoded_name = quote(
        path_name,
        safe="",
    )

    return f"{MEDIAMTX_API_URL}/v3/config/paths/{operation}/{encoded_name}"


def _runtime_path_url(
    path_name: str,
) -> str:

    encoded_name = quote(
        path_name,
        safe="",
    )

    return f"{MEDIAMTX_API_URL}/v3/paths/get/{encoded_name}"


# ============================================================
# MediaMTX 상태 조회
# ============================================================


def _get_mediamtx_path_config(
    path_name: str,
) -> dict | None:
    """
    등록된 MediaMTX path 설정을 조회한다.
    """

    response = requests.get(
        _config_path_url(
            "get",
            path_name,
        ),
        timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
    )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise RuntimeError(
            "MediaMTX path 설정 조회에 "
            "실패했습니다. "
            f"path={path_name} "
            f"status={response.status_code}"
        )

    data = response.json()

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError("MediaMTX path 설정 응답이 올바르지 않습니다.")

    return data


def _get_mediamtx_runtime_path(
    path_name: str,
) -> dict | None:
    """
    현재 활성화된 MediaMTX path 상태 조회.
    """

    response = requests.get(
        _runtime_path_url(path_name),
        timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
    )

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise RuntimeError(
            "MediaMTX path 상태 조회에 "
            "실패했습니다. "
            f"path={path_name} "
            f"status={response.status_code}"
        )

    data = response.json()

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError("MediaMTX path 상태 응답이 올바르지 않습니다.")

    return data


def _is_mediamtx_path_ready(
    path_name: str,
) -> bool:
    """
    MediaMTX path가 실제 재생 가능한 상태인지 확인한다.

    online=True는 source 프로세스가 실행 중이라는 뜻일 뿐,
    실제 영상 track이 준비되었다는 의미는 아니다.

    KTICT HLS 인증 만료 등으로 source가 죽으면
    online=True 상태에서도
    ready=False / available=False / tracks=[]가 될 수 있다.
    """

    data = _get_mediamtx_runtime_path(path_name)

    if data is None:
        return False

    tracks = data.get("tracks") or []

    return (
        bool(data.get("online", False))
        and bool(data.get("ready", False))
        and bool(data.get("available", False))
        and bool(tracks)
    )


# ============================================================
# MediaMTX Path 설정 비교
# ============================================================


def _path_config_matches(
    current: dict,
    desired: dict,
) -> bool:
    """
    이미 동일한 설정이면 PATCH를 생략한다.

    MediaMTX PATCH는 configuration reload를 일으키므로
    불필요한 reload와 source 재연결을 방지한다.
    """

    current_source = str(
        current.get(
            "source",
            "",
        )
        or ""
    )

    desired_source = str(
        desired.get(
            "source",
            "",
        )
        or ""
    )

    current_fingerprint = str(
        current.get(
            "sourceFingerprint",
            "",
        )
        or ""
    )

    desired_fingerprint = str(
        desired.get(
            "sourceFingerprint",
            "",
        )
        or ""
    )

    current_on_demand = bool(
        current.get(
            "sourceOnDemand",
            False,
        )
    )

    desired_on_demand = bool(
        desired.get(
            "sourceOnDemand",
            False,
        )
    )

    return (
        current_source == desired_source
        and current_fingerprint == desired_fingerprint
        and current_on_demand == desired_on_demand
    )


# ============================================================
# MediaMTX Control API
# ============================================================


def _upsert_mediamtx_path(
    path_name: str,
    source_url: str,
    source_fingerprint: str,
    *,
    keep_warm: bool,
    force_reload: bool = False,
) -> None:
    """
    MediaMTX path 생성 또는 갱신.

    keep_warm=True:
        sourceOnDemand=False
        → 등록 즉시 원본 CCTV source 연결
        → 감시 중인 동안 source 유지

    keep_warm=False:
        sourceOnDemand=True
        → 브라우저 reader가 있을 때만 source 연결
    """

    payload = {
        "source": source_url,
        "sourceOnDemand": not keep_warm,
        "sourceOnDemandStartTimeout": SOURCE_ON_DEMAND_START_TIMEOUT,
        "sourceOnDemandCloseAfter": SOURCE_ON_DEMAND_CLOSE_AFTER,
        "sourceFingerprint": source_fingerprint,
    }

    # --------------------------------------------------------
    # 현재 설정 조회
    # --------------------------------------------------------

    current = _get_mediamtx_path_config(path_name)

    # --------------------------------------------------------
    # 이미 같은 설정이면 아무것도 하지 않는다.
    # --------------------------------------------------------

    if (
        current is not None
        and not force_reload
        and _path_config_matches(
            current,
            payload,
        )
    ):
        print(
            "[CCTV STREAM] "
            "MediaMTX path 설정 유지 "
            f"/ path={path_name} "
            f"/ keep_warm={keep_warm}"
        )

        return

    # --------------------------------------------------------
    # 기존 path 갱신
    # --------------------------------------------------------

    if current is not None:
        response = requests.patch(
            _config_path_url(
                "patch",
                path_name,
            ),
            json=payload,
            timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"MediaMTX path 갱신에 실패했습니다. path={path_name} status={response.status_code}"
            )

        print(f"[CCTV STREAM] MediaMTX path 갱신 / path={path_name} / keep_warm={keep_warm}")

        return

    # --------------------------------------------------------
    # 신규 path 생성
    # --------------------------------------------------------

    response = requests.post(
        _config_path_url(
            "add",
            path_name,
        ),
        json=payload,
        timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"MediaMTX path 생성에 실패했습니다. path={path_name} status={response.status_code}"
        )

    print(f"[CCTV STREAM] MediaMTX path 생성 / path={path_name} / keep_warm={keep_warm}")


# ============================================================
# Stream Response
# ============================================================


def _stream_response(
    cctv_id: int,
) -> dict:

    path_name = _path_name(cctv_id)

    playback_url = f"{MEDIAMTX_WEBRTC_BASE_URL}/{path_name}"

    whep_url = f"{playback_url}/whep"

    return {
        "cctv_id": cctv_id,
        "path": path_name,
        "playback_url": playback_url,
        "whep_url": whep_url,
    }


# ============================================================
# 단일 CCTV Prewarm
# ============================================================


def prewarm_cctv_stream(
    cctv_id: int,
    external_cctv_id: str,
) -> dict:
    """
    감시 중 CCTV의 MediaMTX source를
    미리 연결한다.

    최신 UTIC Stream URL을 조회한 뒤
    sourceOnDemand=False path를 구성한다.
    """

    (
        stream_url,
        _,
    ) = get_utic_stream_url(external_cctv_id)

    (
        source_url,
        source_fingerprint,
    ) = _build_mediamtx_source(stream_url)

    path_name = _path_name(cctv_id)

    _upsert_mediamtx_path(
        path_name=path_name,
        source_url=source_url,
        source_fingerprint=(source_fingerprint),
        keep_warm=True,
    )

    return _stream_response(cctv_id)


# ============================================================
# 감시 중 CCTV 전체 Prewarm
# ============================================================


def prewarm_monitored_cctv_streams() -> dict:
    """
    DB에서 현재 감시 중인 UTIC CCTV를 조회하여
    모두 MediaMTX에 미리 연결한다.

    특정 CCTV 하나가 실패해도
    다른 CCTV prewarm은 계속 진행한다.
    """

    # 순환 import 방지
    from backend.app.cctvs import (
        repository,
    )

    from backend.app.db.session import (
        get_connection,
    )

    with get_connection() as connection:
        rows = repository.list_monitored_utic_cctvs(connection)

    success = 0
    failed = 0

    print(f"[CCTV STREAM PREWARM] 감시 중 CCTV {len(rows)}대 준비 시작")

    for row in rows:
        try:
            prewarm_cctv_stream(
                cctv_id=int(row["id"]),
                external_cctv_id=str(row["external_cctv_id"]),
            )

            success += 1

        except Exception as exc:
            failed += 1

            print(
                "[CCTV STREAM PREWARM WARNING] "
                f"CCTV {row['id']} 실패 "
                f"/ type={type(exc).__name__} "
                f"/ error={exc}"
            )

    print(f"[CCTV STREAM PREWARM] 완료 / success={success} / failed={failed}")

    return {
        "total": len(rows),
        "success": success,
        "failed": failed,
    }


# ============================================================
# CCTV Stream 제거
# ============================================================


def remove_cctv_stream(
    cctv_id: int,
) -> None:
    """
    CCTV 감시가 OFF가 될 때
    MediaMTX path를 제거한다.

    MediaMTX가 내려가 있거나 path가 없어도
    CCTV 감시 상태 변경 자체는 실패시키지 않는다.
    """

    path_name = _path_name(cctv_id)

    try:
        response = requests.delete(
            _config_path_url(
                "delete",
                path_name,
            ),
            timeout=(MEDIAMTX_REQUEST_TIMEOUT_SEC),
        )

        if response.status_code in {
            200,
            404,
        }:
            print(f"[CCTV STREAM] MediaMTX path 제거 / cctv_id={cctv_id}")

            return

        print(
            "[CCTV STREAM WARNING] "
            "MediaMTX path 삭제 실패 "
            f"/ cctv_id={cctv_id} "
            f"/ status={response.status_code}"
        )

    except requests.RequestException as exc:
        print(
            f"[CCTV STREAM WARNING] MediaMTX path 삭제 요청 실패 / cctv_id={cctv_id} / error={exc}"
        )


# ============================================================
# CCTV Stream 준비
# ============================================================


def prepare_cctv_stream(
    cctv_id: int,
    external_cctv_id: str,
) -> dict:
    """
    W04에서 CCTV 영상을 요청할 때 호출한다.

    이미 MediaMTX source가 실제 재생 가능한
    ready 상태라면 UTIC 재조회나
    MediaMTX PATCH 없이 바로 WebRTC 주소를 반환한다.

    source가 없거나 실제 재생 불가능한 상태라면
    최신 UTIC Stream URL을 다시 조회하고
    MediaMTX path를 강제로 reload한다.
    """

    path_name = _path_name(cctv_id)

    # --------------------------------------------------------
    # 이미 source가 online이면 즉시 반환
    # --------------------------------------------------------

    try:
        if _is_mediamtx_path_ready(path_name):
            print(
                "[CCTV STREAM] "
                "기존 ready source 재사용 "
                f"/ cctv_id={cctv_id}"
            )

            return _stream_response(cctv_id)

    except requests.RequestException:
        pass

    # --------------------------------------------------------
    # source 없음 / 재생 불가
    # --------------------------------------------------------

    (
        stream_url,
        _,
    ) = get_utic_stream_url(external_cctv_id)

    (
        source_url,
        source_fingerprint,
    ) = _build_mediamtx_source(stream_url)

    _upsert_mediamtx_path(
        path_name=path_name,
        source_url=source_url,
        source_fingerprint=source_fingerprint,
        keep_warm=True,
        force_reload=True,
    )

    return _stream_response(cctv_id)
