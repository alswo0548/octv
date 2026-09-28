"""인증·회원가입 HTTP 진입점. 현재 업무 API는 501(미구현)을 반환합니다."""

from fastapi import APIRouter
from . import schemas, service

router = APIRouter(prefix="/auth", tags=["인증·회원가입"])
# TODO: 구현하는 API부터 dependencies의 인증·권한 검사를 연결하세요.


@router.post("/login", summary="login · 구현 예정")
def login(body: schemas.LoginRequest):
    return service.login(body)


@router.post("/signup", summary="signup · 구현 예정")
def signup(body: schemas.SignupRequest):
    return service.signup(body)


@router.post("/email-check", summary="check_email · 구현 예정")
def check_email(body: schemas.EmailCheckRequest):
    return service.check_email(body)
