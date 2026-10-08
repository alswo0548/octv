from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,       # 이메일 형식인지 검사
    Field,
    SecretStr,      # 비밀번호를 일반 문자열보다 조금 안전하게 다루기 위한 Pydantic 타입. 객체 자체를 출력했을 때 비밀번호가 그대로 노출되는 걸 줄여줌.
    field_validator,
)


# 일반 회원가입에서 선택 가능한 역할
SignupRole = Literal["AGENCY_STAFF", "RESPONDER"]


# 로그인할 때 필요한 데이터
class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr

# 회원 가입 시에도 로그인할 때 필요한 데이터가 필요하므로 LoginRequest 상속.
class SignupRequest(LoginRequest):
    name: str = Field(min_length=1, max_length=100)
    role: SignupRole
    agency_id: int = Field(gt=0)

    # 이름 검증
    @field_validator("name")        # 특정 필드만 검사하는 함수를 등록하는 역할
    @classmethod
    def validate_name(cls, value: str) -> str:      # cls : SingupRequest class 자체 -> SignupRequest 클래스에 속하는 함수. value == 'name'이 들어옴.
        value = value.strip()    # 이름 앞뒤 공백을 제거

        if not value:       # 공백만 입력시 오류 발생
            raise ValueError("이름을 입력해 주세요.")

        return value

    # password 검증.
    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()     # SecretStr 안에 있는 실제 비밀번호를 가져옴.

        if not 8 <= len(password) <= 10:
            raise ValueError("비밀번호는 8~10자여야 합니다.")

        if not any(char.isalpha() and char.isascii() for char in password):     # 영문자가 하나라도 포함되어 있는지 검증.
            raise ValueError("비밀번호에는 영문자가 포함되어야 합니다.")

        if not any(char.isdigit() for char in password):        # 숫자가 하나라도 포함되어 있는지 검증.
            raise ValueError("비밀번호에는 숫자가 포함되어야 합니다.")

        if any(char.isspace() for char in password):        # 비밀번호에 공백이 들어가 있는지 검증. -> 들어있으면 에러
            raise ValueError("비밀번호에는 공백을 사용할 수 없습니다.")

        if not any(not char.isalnum() for char in password):        # 특수문자가 하나라도 포함되어 있는지 검증.
            raise ValueError("비밀번호에는 특수문자가 포함되어야 합니다.")

        return value



class EmailCheckRequest(BaseModel):     # email 중복 확인용 버튼을 위해 필요한 field
    email: EmailStr


class EmailCheckResponse(BaseModel):        # 중복 되어있으면 false, 중복 아니면 true 리턴
    available: bool


# 회원가입 성공 후 프론트로 보내줄 사용자 정보의 모양
# password_hash는 API 응답으로 보내지 않음.
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


# OAuth2 로그인을 위한 간단한 응답
class TokenResponse(BaseModel):
    access_token: str
    token_type: str