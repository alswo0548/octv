"""
CCTV 조회·감시 상태: 연결 상태와 감시 상태를 분리하세요. ALERT 중 OFF 거절, 해제 후 POST_ALERT 유지, 확인한 관리자만 수동 OFF.
시간·AI 자동 OFF 금지.
"""

from ..errors import FeatureNotImplemented
from . import schemas


def list_cctvs():
    # TODO: 연결 상태와 감시 상태를 분리하세요. ALERT 중 OFF 거절, 해제 후 POST_ALERT 유지, 확인한 관리자만 수동 OFF.
    # 시간·AI 자동 OFF 금지.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("CCTV 조회·감시 상태 / list_cctvs 구현 예정")


def get_cctv(cctv_id: int):
    # TODO: 연결 상태와 감시 상태를 분리하세요. ALERT 중 OFF 거절, 해제 후 POST_ALERT 유지, 확인한 관리자만 수동 OFF.
    # 시간·AI 자동 OFF 금지.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("CCTV 조회·감시 상태 / get_cctv 구현 예정")


def change_monitoring(cctv_id: int, body: schemas.MonitoringRequest):
    # TODO: 연결 상태와 감시 상태를 분리하세요. ALERT 중 OFF 거절, 해제 후 POST_ALERT 유지, 확인한 관리자만 수동 OFF.
    # 시간·AI 자동 OFF 금지.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("CCTV 조회·감시 상태 / change_monitoring 구현 예정")
