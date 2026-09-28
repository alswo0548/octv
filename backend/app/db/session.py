"""DB 접속·트랜잭션 작업 위치. 아직 드라이버 설치나 접속은 없습니다."""

from ..errors import FeatureNotImplemented


def get_connection():
    # TODO: PostgreSQL 드라이버를 결정·고정한 뒤 config의 DATABASE_URL로 연결하세요.
    # 요청마다 연결을 빌리고 반환하며, 실패 시 rollback하도록 구현하세요.
    # SQL은 기능별 repository.py에 작성하고 파라미터 바인딩을 사용하세요.
    # DDL은 서버 시작 때 자동 실행하지 않습니다. SQL 정의를 중복 작성하지 마세요.
    raise FeatureNotImplemented("PostgreSQL 연결을 구현해야 합니다.")
