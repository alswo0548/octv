"""인증·회원가입: 이메일 중복 확인, 비밀번호 해시, 역할별 로그인, 계정 활성 여부를 구현하세요. 이메일 비교는 DB의 lower(btrim(email)) UNIQUE 기준을 따르세요."""

from ..errors import FeatureNotImplemented
from . import schemas


def login(body: schemas.LoginRequest):
    # TODO: 이메일 중복 확인, 비밀번호 해시, 역할별 로그인, 계정 활성 여부를 구현하세요. 이메일 비교는 DB의 lower(btrim(email)) UNIQUE 기준을 따르세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("인증·회원가입 / login 구현 예정")


def signup(body: schemas.SignupRequest):
    # TODO: 이메일 중복 확인, 비밀번호 해시, 역할별 로그인, 계정 활성 여부를 구현하세요. 이메일 비교는 DB의 lower(btrim(email)) UNIQUE 기준을 따르세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("인증·회원가입 / signup 구현 예정")


def check_email(body: schemas.EmailCheckRequest):
    # TODO: 이메일 중복 확인, 비밀번호 해시, 역할별 로그인, 계정 활성 여부를 구현하세요. 이메일 비교는 DB의 lower(btrim(email)) UNIQUE 기준을 따르세요.
    # repository에서 조회/저장한 결과를 schemas 형식으로 변환하세요.
    raise FeatureNotImplemented("인증·회원가입 / check_email 구현 예정")
