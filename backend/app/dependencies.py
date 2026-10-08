"""FastAPI Depends에 연결할 공통 인증·권한 작업 위치."""

import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from .auth import repository
from .auth.service import JWT_ALGORITHM
from .config import jwt_secret
from .db.session import get_connection


# HTTP 요청의 Authorization 헤더에서 Bearer token을 꺼내주는 것
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token"
)


def get_current_user(       # 요청에서 JWT를 받아서 현재 로그인한 사용자를 찾아 반환하는 함수
    token: str = Depends(oauth2_scheme),        # token 변수에 Authorization 헤더에서 Bearer token 확인해서 JWT 문자열을 넣어줌.
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},     # Bearer token 인증이 필요함을 알려주는 표준적인 방식
    )

    try:
        payload = jwt.decode(
            token,
            jwt_secret(),
            algorithms=[JWT_ALGORITHM],
        )

        subject = payload.get("sub")        # 토큰이 누구의 것인지 나타내는 값. users.id값 꺼냄

        if subject is None:
            raise credentials_exception

        user_id = int(subject)      # str -> int로 변환

    except (
        ExpiredSignatureError,      # JWT 토큰 만료
        InvalidTokenError,          # 잘못된 JWT
        ValueError,                 # int(subject)가 실패. ex) subject = 'abc'인 경우
        TypeError,                  # sub 값 타입 자체가 이상함
    ):
        raise credentials_exception

    with get_connection() as connection:
        user = repository.find_user_by_id(
            connection,
            user_id,
        )

    if user is None:
        raise credentials_exception

    # 비활성 계정 확인
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    return user


# 로그인 여부를 넘어서 역할까지 검사하는 함수
def require_control_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "CONTROL_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관제 관리자 권한이 필요합니다.",
        )

    return current_user
