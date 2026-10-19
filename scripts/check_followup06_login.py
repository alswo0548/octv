r"""로컬 OCTV 서버에서 검증 계정 3개의 실제 로그인·JWT 본인 조회를 확인합니다.

먼저 backend/.env와 분석·푸시 OFF 설정을 적용한 Uvicorn을 실행합니다.
실행: python scripts\check_followup06_login.py

범위: 서버 OpenAPI 확인 → 비밀번호 숨김 입력 → 로그인 3회 → 본인 조회 3회.
현재 단계에서 준비한 사용자/기관 ID를 EXPECTED에서 명시적으로 확인합니다.
비밀번호·JWT·응답 본문·헤더·예외 원문은 출력하거나 파일에 저장하지 않습니다.
DB 변경 API, 외부 API, 알림·기기 등록 API는 호출하지 않습니다.
"""

from __future__ import annotations

import getpass
import warnings

import httpx


BASE_URL = "http://127.0.0.1:8000"
# prepare_followup06_test_data.py 실행 결과: 현재 검증 환경의 실제 ID입니다.
EXPECTED = (
    ("admin", "octv06.admin@example.com", 1, "CONTROL_ADMIN", None),
    ("agency_a", "octv06.agency.a@example.com", 2, "AGENCY_STAFF", 1),
    ("agency_b", "octv06.agency.b@example.com", 3, "RESPONDER", 2),
)


class CheckFailed(Exception):
    """외부 응답을 포함하지 않는 고정 실패 코드만 사용합니다."""


def read_json(response):
    if response.status_code != 200:
        raise CheckFailed(f"HTTP_{response.status_code}")
    value = response.json()
    if not isinstance(value, dict):
        raise CheckFailed("RESPONSE_OBJECT_REQUIRED")
    return value


def check_identity(user, email, user_id, role, agency_id):
    if not isinstance(user, dict):
        raise CheckFailed("USER_OBJECT_REQUIRED")
    if (
        type(user.get("id")) is not int
        or user["id"] != user_id
        or user.get("email") != email
        or user.get("role") != role
        or user.get("is_active") is not True
        or user.get("agency_id") != agency_id
        or (agency_id is not None and type(user.get("agency_id")) is not int)
    ):
        raise CheckFailed("EXPECTED_TEST_USER_MISMATCH")


def run(client, password):
    passed = 0
    for label, email, user_id, role, agency_id in EXPECTED:
        stage = label + " LOGIN"
        try:
            login = read_json(client.post(
                "/api/auth/login", json={"email": email, "password": password}
            ))
            token = login.get("access_token")
            if (
                not isinstance(token, str) or not token.strip()
                or login.get("token_type") != "bearer"
            ):
                raise CheckFailed("BEARER_TOKEN_REQUIRED")
            check_identity(login.get("user"), email, user_id, role, agency_id)
            passed += 1
            print(f"PASS: {stage} HTTP_200", flush=True)

            stage = label + " ME"
            me = read_json(client.get(
                "/api/auth/me", headers={"Authorization": "Bearer " + token}
            ))
            check_identity(me, email, user_id, role, agency_id)
            del token, login, me
            passed += 1
            print(
                f"PASS: {stage} HTTP_200 user_id={user_id} role={role} agency_id={agency_id}",
                flush=True,
            )
        except CheckFailed as exc:
            print(f"FAIL: {stage} {exc}; passed={passed}/6")
            return 1
        except Exception as exc:
            print(f"FAIL: {stage} {type(exc).__name__}; passed={passed}/6")
            return 1
    print("LOGIN_CHECK_PASSED: 6/6")
    return 0


def main():
    stage = "SERVER_CHECK"
    try:
        # 로컬 요청에 프록시 환경변수나 HTTP 리다이렉트를 적용하지 않습니다.
        with httpx.Client(
            base_url=BASE_URL, timeout=10.0, trust_env=False, follow_redirects=False
        ) as client:
            spec = read_json(client.get("/openapi.json"))
            info = spec.get("info")
            paths = spec.get("paths")
            if (
                not isinstance(info, dict)
                or not isinstance(info.get("title"), str)
                or not info["title"].startswith("OCTV")
                or not isinstance(paths, dict)
                or "post" not in paths.get("/api/auth/login", {})
                or "get" not in paths.get("/api/auth/me", {})
            ):
                raise CheckFailed("EXPECTED_OCTV_AUTH_SERVER_REQUIRED")
            print("SERVER_CHECK: OCTV auth endpoints found")
            stage = "PASSWORD_INPUT"
            # 숨김 입력을 지원하지 않는 환경에서는 비밀번호를 표시하지 않고 중단합니다.
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Test password (hidden): ")
            stage = "LOGIN_CHECK"
            return run(client, password)
    except CheckFailed as exc:
        print(f"FAIL: {stage} {exc}")
        return 1
    except (KeyboardInterrupt, EOFError):
        print("LOGIN_CHECK_CANCELLED")
        return 2
    except Exception as exc:
        print(f"FAIL: {stage} {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
