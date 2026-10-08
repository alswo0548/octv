"""인증·회원가입 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from . import service
from .schemas import (
    EmailCheckRequest,
    EmailCheckResponse,
    LoginRequest,
    SignupRequest,
    UserResponse,
    LoginResponse,
    TokenResponse,
)

from ..dependencies import get_current_user


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


# 로그인
@router.post(
    "/login",
    response_model=LoginResponse,
)
def login(payload: LoginRequest):
    return service.login(payload)


# 회원가입
@router.post(
    "/signup",
    response_model=UserResponse,        # 회원가입 성공 응답 : UserResponse 형식.
    status_code=status.HTTP_201_CREATED,
)
def signup(payload: SignupRequest):
    return service.signup(payload)      # 검증된 요청을 service에게 넘기고, service가 돌려준 결과를 그대로 응답


# 이메일 중복 확인
@router.post(
    "/email-check",
    response_model=EmailCheckResponse,
)
def check_email(payload: EmailCheckRequest):
    return service.check_email(payload)


@router.post(
    "/token",
    response_model=TokenResponse,
)
def issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),       # OAuth2 폼을 읽어줌.
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


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: dict = Depends(get_current_user),
):
    return UserResponse(**current_user)