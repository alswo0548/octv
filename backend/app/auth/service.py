"""인증·회원가입: 이메일 중복 확인, 비밀번호 해시, 역할별 로그인, 계정 활성 여부를 구현하세요. 이메일 비교는 DB의 lower(btrim(email)) UNIQUE 기준을 따르세요."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from fastapi import HTTPException, status
from psycopg.errors import UniqueViolation

from ..config import jwt_secret
from ..db.session import get_connection
from . import repository
from .schemas import (
    EmailCheckRequest,
    EmailCheckResponse,
    LoginRequest,
    LoginResponse,
    SignupRequest,
    UserResponse,
)
from psycopg.errors import UniqueViolation

from ..db.session import get_connection
from . import repository
from .schemas import (
    EmailCheckRequest,
    EmailCheckResponse,
    LoginRequest,
    SignupRequest,
    UserResponse,
)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60        # JWT 유효기간 60


# JWT 생성 함수 (user_id를 받아서 JWT 문자열을 만들어 반환한다)
def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)        # JWT 발급시간, 만료시간 계산을 위한 현재 시간 구하기

    payload = {
        "sub": str(user_id),        # 누구의 토큰인지 확인
        "iat": now,     # JWT가 언제 발급됐는지를 의미
        "exp": now + timedelta(     # 토큰 만료시간
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        ),
    }

    # 실제 JWT 문자열 만드는 만드는 부분
    return jwt.encode(
        payload,            # JWT 안에 넣을 데이터
        jwt_secret(),       # 비밀키
        algorithm=JWT_ALGORITHM,        # 사용 알고리즘
    )


# 로그인
def login(payload: LoginRequest) -> LoginResponse:
    # 이메일 비교 기준 통일
    email = str(payload.email).strip().lower()

    # 사용자가 입력한 실제 비밀번호
    password = payload.password.get_secret_value()

    with get_connection() as connection:
        # 1. 이메일로 사용자 조회
        user = repository.find_user_by_email(
            connection,
            email,
        )

        # 2. 사용자 존재 여부 확인
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        # 3. 비밀번호 확인
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"),       # 입력된 비밀번호(문자열)을 bytes 형태로 변환해서 비교
            user["password_hash"].encode("utf-8"),
        )

        if not password_matches:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            )

        # 4. 계정 활성 여부 확인
        if not user["is_active"]:       # user의 is_active 가 false 이면 -> True가 되어서 error 발생시킴.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="비활성화된 계정입니다.",
            )

        # 5. JWT access token 발급
        access_token = create_access_token(
            user_id=user["id"]
        )

        # 6. 로그인 결과 반환
        return LoginResponse(
            access_token=access_token,      # JWT access token
            token_type="bearer",
            user=UserResponse(**user),
        )


# 이메일 중복 확인
def check_email(payload: EmailCheckRequest) -> EmailCheckResponse:
    # EmailStr → 일반 문자열 변환
    # 앞뒤 공백 제거 + 소문자로 통일
    email = str(payload.email).strip().lower()      # EmailStr 값 문자열로 변환 후 공백제거, 소문자로 변환

    with get_connection() as connection:        # db와 connection 열어 repository에서 만든 함수 실행
        user = repository.find_user_by_email(
            connection,
            email,
        )       # db에 이메일 존재하면 user = {...}, 존재하지 않으면 None

    # 사용자가 없으면 사용 가능한 이메일
    if user is None:
        available = True
    else:
        available = False

    return EmailCheckResponse(
        available=available
    )


# 회원가입
def signup(payload: SignupRequest) -> UserResponse:     # payload : Pydantic 검증까지 통과한 회원가입 정보가 들어 있음. 
    # 이메일 저장 형식 통일
    email = str(payload.email).strip().lower()      # 사용자가 반드시 중복 확인 API를 먼저 호출한다는 보장이 없기 때문에 이메일 정규화

    # SecretStr 안의 실제 비밀번호 가져오기. payload.password는 일반 str이 아니기 때문에 get_secret_value()를 이용해 실제 비밀번호 값 볼 수 있음.
    password = payload.password.get_secret_value()

    try:
        with get_connection() as connection:    # 회원가입이라는 하나의 작업을 하나의 DB transaction 안에서 처리

            # 1. 이메일 중복 확인
            existing_user = repository.find_user_by_email(
                connection,
                email,
            )

            if existing_user is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="이미 사용 중인 이메일입니다.",
                )

            # 2. 실제 존재하는 기관인지 확인
            if not repository.agency_exists(
                connection,
                payload.agency_id,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="존재하지 않는 기관입니다.",
                )

            # 3. 비밀번호 bcrypt 해시
            password_hash = bcrypt.hashpw(      # 비밀번호 hash 생성
                password.encode("utf-8"),       # Python 문자열을 bytes로 바꿈
                bcrypt.gensalt(),       # salt 생성
            ).decode("utf-8")       # bytes -> str으로 바꿔서 db에 저장.

            # 4. 사용자 DB 저장
            user = repository.insert_user(
                connection,
                {
                    "email": email,
                    "password_hash": password_hash,
                    "name": payload.name,
                    "role": payload.role,
                    "agency_id": payload.agency_id,
                },
            )

            # 5. 프론트에 반환할 형태로 변환
            return UserResponse(**user)

    # 동시에 같은 이메일로 회원가입 요청이 들어온 경우
    # DB UNIQUE 제약조건이 최종적으로 차단. DB에서 차단 시 UniqueViolation 발생.
    except UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )


# ============================================================
# 회원가입용 지역 / 기관 조회
# ============================================================

def list_signup_sidos() -> list[dict]:
    """
    회원가입 화면에서 사용할 시·도 목록을 반환한다.
    """

    with get_connection() as connection:
        return repository.list_signup_sidos(
            connection
        )


def list_signup_sigungus(
    sido_name: str,
) -> list[dict]:
    """
    선택한 시·도에 속한 시·군·구 목록을 반환한다.
    """

    sido_name = sido_name.strip()

    if not sido_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="시·도를 선택해 주세요.",
        )

    with get_connection() as connection:
        return repository.list_signup_sigungus(
            connection,
            sido_name,
        )


def list_signup_agencies(
    region_code: str,
    agency_type: str | None = None,
) -> list[dict]:
    """
    선택한 지역과 기관 유형에 맞는
    소속기관 목록을 반환한다.
    """

    region_code = region_code.strip()

    if not region_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지역을 선택해 주세요.",
        )

    with get_connection() as connection:
        return repository.list_signup_agencies(
            connection,
            region_code,
            agency_type,
        )