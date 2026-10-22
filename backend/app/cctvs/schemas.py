"""CCTV 조회·감시 상태 API Schema. DB의 마지막 프레임 KST 시각을 UTC로 반환합니다."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel, field_validator


KST = ZoneInfo("Asia/Seoul")


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

    @field_validator("last_frame_at")
    @classmethod
    def explicit_utc(cls, value):
        if value is None:
            return None
        # Runtime은 KST 시각을 TIMESTAMP WITHOUT TIME ZONE에 저장한다.
        # 시간대 없는 DB 값은 KST로 해석한 뒤 UTC로 변환한다.
        if value.tzinfo is None:
            value = value.replace(tzinfo=KST)
        return value.astimezone(timezone.utc)


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


class CctvReconnectResponse(BaseModel):
    """
    관리자 수동 CCTV 재연결 요청 접수 응답.

    ACCEPTED는 실제 재연결 완료가 아니라
    Runtime에 전달할 요청이 접수되었다는 의미다.
    """

    cctv_id: int
    status: Literal["ACCEPTED"] = "ACCEPTED"