"""인증·회원가입 입출력 초안. SQL 구조와 UI 단위를 확인하며 완성하세요."""

from pydantic import BaseModel, SecretStr
from typing import Literal


class LoginRequest(BaseModel):
    email: str
    password: SecretStr


class SignupRequest(LoginRequest):
    name: str
    # TODO: 일반 가입에서 관리자 권한을 스스로 선택하지 못하도록 서버 정책을 적용하세요.
    role: Literal["CONTROL_ADMIN", "AGENCY_STAFF", "RESPONDER"]
    agency_id: int | None = None


class EmailCheckRequest(BaseModel):
    email: str


class UserResponse(BaseModel):
    id: int
    name: str
    role: str
    agency_id: int | None = None
    # 비밀번호와 password_hash는 응답에 포함하지 않습니다.
