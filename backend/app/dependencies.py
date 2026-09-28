"""FastAPI Depends에 연결할 공통 인증·권한 작업 위치."""

from .errors import FeatureNotImplemented


def get_current_user():
    # TODO: 토큰 확인 → 활성 사용자 조회. 가짜 로그인 사용자 반환 금지.
    raise FeatureNotImplemented("사용자 인증·권한 확인을 구현해야 합니다.")


def require_control_admin():
    # TODO: get_current_user 결과의 CONTROL_ADMIN 권한을 검사하세요.
    # CCTV 감시 변경·시스템 설정·기관 전달 API에 적용하세요.
    raise FeatureNotImplemented("관리자 권한 확인을 구현해야 합니다.")
