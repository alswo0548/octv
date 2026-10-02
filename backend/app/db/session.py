"""psycopg 공통 연결. 정상 종료 commit, 예외 rollback, 항상 close."""

from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from ..config import database_connect_kwargs


@contextmanager
def get_connection():
    # 사용: with get_connection() as connection: repository.some_query(connection)
    # 업무 단위 전체를 하나의 with 블록으로 묶습니다. DDL은 자동 실행하지 않습니다.
    with psycopg.connect(**database_connect_kwargs(), row_factory=dict_row) as connection:
        yield connection
