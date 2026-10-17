"""프로젝트 위치 기준 .env 로딩. 서버 기동 자체는 DB에 접속하지 않습니다."""

import os
from pathlib import Path

from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]

# OCTV의 DB 세션 시간대
DB_TIMEZONE = "Asia/Seoul"


def database_connect_kwargs() -> dict:
    """
    DATABASE_URL 우선,
    비어 있으면 루트 POSTGRES_* 사용.

    OCTV에서 생성하는 PostgreSQL 연결은
    모두 Asia/Seoul 시간대를 사용한다.

    비밀값 출력 금지.
    """

    backend_values = dotenv_values(
        ROOT / "backend" / ".env",
        interpolate=False,
    )

    url = os.environ.get(
        "DATABASE_URL",
        backend_values.get("DATABASE_URL"),
    )

    # =====================================================
    # DATABASE_URL 사용
    # =====================================================

    if url and url.strip():
        return {
            "conninfo": url.strip(),
            "connect_timeout": 5,

            # PostgreSQL 세션 시간대를 KST로 설정
            "options": (
                f"-c timezone={DB_TIMEZONE}"
            ),
        }

    # =====================================================
    # 루트 .env의 POSTGRES_* 사용
    # =====================================================

    values = dotenv_values(
        ROOT / ".env",
        interpolate=False,
    )

    def value(
        key,
        default=None,
    ):
        return os.environ.get(
            key,
            values.get(
                key,
                default,
            ),
        )

    password = value(
        "POSTGRES_PASSWORD"
    )

    if not password:
        raise ValueError(
            "루트 .env에 "
            "POSTGRES_PASSWORD를 설정하세요."
        )

    try:
        port = int(
            value(
                "POSTGRES_PORT",
                "5432",
            )
        )

    except (
        TypeError,
        ValueError,
    ) as exc:

        raise ValueError(
            "POSTGRES_PORT는 숫자여야 합니다."
        ) from exc

    if not 1 <= port <= 65535:
        raise ValueError(
            "POSTGRES_PORT는 "
            "1~65535 범위여야 합니다."
        )

    return {
        "host": "127.0.0.1",
        "port": port,
        "dbname": value(
            "POSTGRES_DB",
            "octv_dev",
        ),
        "user": value(
            "POSTGRES_USER",
            "octv_dev",
        ),
        "password": password,
        "connect_timeout": 5,

        # PostgreSQL 세션 시간대를 KST로 설정
        "options": (
            f"-c timezone={DB_TIMEZONE}"
        ),
    }


# =========================================================
# JWT
# =========================================================

def jwt_secret() -> str:
    """JWT_SECRET 값을 가져온다."""

    backend_values = dotenv_values(
        ROOT / "backend" / ".env",
        interpolate=False,
    )

    secret = os.environ.get(
        "JWT_SECRET",
        backend_values.get(
            "JWT_SECRET"
        ),
    )

    if (
        not secret
        or not secret.strip()
    ):
        raise ValueError(
            "backend/.env에 "
            "JWT_SECRET을 설정해야 합니다."
        )

    return secret.strip()