from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)


# ============================================================
# 역할 / 기관 유형
# ============================================================

# 일반 회원가입에서 선택 가능한 역할
SignupRole = Literal[
    "AGENCY_STAFF",
    "RESPONDER",
]

# 회원가입 화면에서 선택 가능한 기관 유형
AgencyType = Literal[
    "FIRE",
    "POLICE",
    "ROAD_MANAGEMENT",
    "LOCAL_GOVERNMENT",
]


# ============================================================
# 로그인 / 회원가입
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class SignupRequest(LoginRequest):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    role: SignupRole

    agency_id: int = Field(
        gt=0,
    )

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:

        value = value.strip()

        if not value:
            raise ValueError(
                "이름을 입력해 주세요."
            )

        return value

    @field_validator("password")
    @classmethod
    def validate_password(
        cls,
        value: SecretStr,
    ) -> SecretStr:

        password = (
            value.get_secret_value()
        )

        if not 8 <= len(password) <= 10:
            raise ValueError(
                "비밀번호는 8~10자여야 합니다."
            )

        if not any(
            char.isalpha()
            and char.isascii()
            for char in password
        ):
            raise ValueError(
                "비밀번호에는 영문자가 "
                "포함되어야 합니다."
            )

        if not any(
            char.isdigit()
            for char in password
        ):
            raise ValueError(
                "비밀번호에는 숫자가 "
                "포함되어야 합니다."
            )

        if any(
            char.isspace()
            for char in password
        ):
            raise ValueError(
                "비밀번호에는 공백을 "
                "사용할 수 없습니다."
            )

        if not any(
            not char.isalnum()
            for char in password
        ):
            raise ValueError(
                "비밀번호에는 특수문자가 "
                "포함되어야 합니다."
            )

        return value


# ============================================================
# 이메일 중복 확인
# ============================================================

class EmailCheckRequest(BaseModel):
    email: EmailStr


class EmailCheckResponse(BaseModel):
    available: bool


# ============================================================
# 회원가입 지역 / 기관 선택
# ============================================================

class SignupSidoResponse(BaseModel):
    sido_name: str


class SignupSigunguResponse(BaseModel):
    region_code: str
    sigungu_name: str


class SignupAgencyResponse(BaseModel):
    id: int
    name: str
    agency_type: AgencyType
    address: str | None = None
    region_code: str


# ============================================================
# 사용자 / 로그인 응답
# ============================================================

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str
    agency_id: int | None = None
    is_active: bool
    notification_enabled: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class TokenResponse(BaseModel):
    access_token: str
    token_type: str