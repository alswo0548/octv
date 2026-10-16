"""CCTV 조회·감시 상태 API Schema."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ConnectionStatus = Literal[
    "CONNECTED",
    "DISCONNECTED",
    "RECONNECTING",
]

VideoQualityStatus = Literal[
    "GOOD",
    "LOW",
    "UNAVAILABLE",
]

AnalysisStatus = Literal[
    "RUNNING",
    "STOPPED",
    "ERROR",
]

MonitoredMode = Literal[
    "BASE",
    "ALERT",
    "VERIFY",
    "POST_ALERT",
    "OFF",
]


class CctvResponse(BaseModel):
    id: int

    external_cctv_id: str

    name: str

    provider: str

    address: str | None = None

    latitude: float

    longitude: float

    is_monitored: bool

    connection_status: ConnectionStatus

    video_quality_status: (
        VideoQualityStatus
        | None
    ) = None

    analysis_status: (
        AnalysisStatus
        | None
    ) = None

    last_frame_at: (
        datetime
        | None
    ) = None

    region_code: str | None = None

    sido_name: str | None = None

    sigungu_name: str | None = None

    monitored_mode: (
        MonitoredMode
        | None
    ) = None


class CctvSummaryResponse(BaseModel):
    total_count: int

    monitored_count: int

    connected_count: int

    disconnected_count: int

    reconnecting_count: int


class MonitoringRequest(BaseModel):
    """
    관리자 CCTV 감시 ON/OFF 요청.

    enabled = True
        -> true + BASE

    enabled = False
        -> false + OFF
    """

    enabled: bool


class CctvStreamResponse(BaseModel):
    """
    W04 CCTV 실시간 영상 재생 정보.

    실제 UTIC source URL은 노출하지 않고
    MediaMTX WebRTC 재생 주소만 반환한다.
    """

    cctv_id: int

    path: str

    playback_url: str

    whep_url: str