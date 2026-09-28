"""DB 조회/저장 작업 위치. SQL은 파라미터 바인딩으로 작성하세요."""

from ..errors import FeatureNotImplemented

# db/session.py의 연결을 전달받습니다. commit/rollback 범위는 서비스에서 관리합니다.


def find_user_by_email(connection, email: str):
    # TODO: users에서 이메일로 조회. password_hash는 서비스 내부에서만 사용.
    raise FeatureNotImplemented("auth.find_user_by_email DB 쿼리 구현 예정")


def insert_user(connection, user_data: dict):
    # TODO: users 등록. 원문 비밀번호 금지, 소속 agencies FK 확인. 동시 가입 중복 방지 정책 필요.
    raise FeatureNotImplemented("auth.insert_user DB 쿼리 구현 예정")
