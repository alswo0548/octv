"""인증·로그인·회원가입 HTTP 진입점."""

from fastapi import (
    APIRouter,
    Depends,
    status,
)
from fastapi.security import (
    OAuth2PasswordRequestForm,
)

from . import service
from .schemas import (
    AgencyType,
    EmailCheckRequest,
    EmailCheckResponse,
    LoginRequest,
    LoginResponse,
    SignupAgencyResponse,
    SignupRequest,
    SignupSidoResponse,
    SignupSigunguResponse,
    TokenResponse,
    UserResponse,
)

from ..dependencies import get_current_user


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


# ============================================================
# 로그인
# ============================================================

@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(
    payload: LoginRequest,
):
    return service.login(
        payload
    )


# ============================================================
# 회원가입
# ============================================================

@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    payload: SignupRequest,
):
    return service.signup(
        payload
    )


# ============================================================
# 이메일 중복 확인
# ============================================================

@router.post(
    "/email-check",
    response_model=EmailCheckResponse,
)
def check_email(
    payload: EmailCheckRequest,
):
    return service.check_email(
        payload
    )


# ============================================================
# 회원가입용 지역 / 기관 조회
# ============================================================

@router.get(
    "/signup/sidos",
    response_model=list[
        SignupSidoResponse
    ],
)
def list_signup_sidos():
    """
    회원가입 화면에서 사용할
    시·도 목록을 조회한다.
    """

    return service.list_signup_sidos()


@router.get(
    "/signup/sigungus",
    response_model=list[
        SignupSigunguResponse
    ],
)
def list_signup_sigungus(
    sido_name: str,
):
    """
    선택한 시·도에 속한
    시·군·구 목록을 조회한다.
    """

    return service.list_signup_sigungus(
        sido_name
    )


@router.get(
    "/signup/agencies",
    response_model=list[
        SignupAgencyResponse
    ],
)
def list_signup_agencies(
    region_code: str,
    agency_type: AgencyType | None = None,
):
    """
    선택한 지역과 기관 유형에 맞는
    소속기관 목록을 조회한다.
    """

    return service.list_signup_agencies(
        region_code,
        agency_type,
    )


# ============================================================
# OAuth2 Token
# ============================================================

@router.post(
    "/token",
    response_model=TokenResponse,
)
def issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    result = service.login(
        LoginRequest(
            email=form_data.username,
            password=form_data.password,
        )
    )

    return TokenResponse(
        access_token=result.access_token,
        token_type=result.token_type,
    )


# ============================================================
# 현재 로그인 사용자
# ============================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: dict = Depends(
        get_current_user
    ),
):
    return UserResponse(
        **current_user
    )