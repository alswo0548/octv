# 브라우저 접속 CORS 설정

## 한 번 설정할 것

1. `ipconfig`로 PC의 현재 Wi-Fi IPv4를 확인합니다.
2. `backend/.env`에 새 설정 `OCTV_CORS_ALLOWED_ORIGINS`를 추가합니다. **브라우저에서 연 페이지의 Origin**을 쉼표로 구분합니다.

```dotenv
OCTV_CORS_ALLOWED_ORIGINS=http://localhost:8081,http://127.0.0.1:8081
```

휴대폰의 페이지 주소가 `http://현재PC주소:8081`이면 그 주소도 목록에 추가합니다. 휴대폰 자체 IP, `/api` 경로, 끝 슬래시, `*`는 넣지 않습니다. 배포에서는 실제 HTTPS 웹 주소를 명시합니다. 환경변수에 같은 이름이 있으면 `.env`보다 우선합니다.

3. `frontend/mobile/.env`의 `EXPO_PUBLIC_API_BASE_URL`에는 **백엔드 주소** `http://현재PC주소:8000`을 입력합니다. 모바일 개발 서버도 다시 실행합니다.

| 설정 | 가리키는 곳 | 개발 포트 |
| --- | --- | --- |
| OCTV_CORS_ALLOWED_ORIGINS | 브라우저에서 연 페이지 | 모바일 웹 8081 |
| EXPO_PUBLIC_API_BASE_URL | API 요청을 받을 백엔드 | 8000 |

관리자 웹 기본 설정은 Vite의 같은 출처 `/api` 프록시를 사용합니다. 웹에서 별도 API 주소를 직접 호출한다면 그 웹페이지 Origin도 허용합니다. 이 프로젝트의 관리자 웹 개발 포트는 4173입니다.

## 매번 실행할 것

프로젝트 루트 CMD에서 실행합니다. 기존 8000 서버가 있으면 그 창에서 Ctrl+C로 종료합니다.

```cmd
.venv\Scripts\python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

휴대폰 브라우저용 모바일 웹은 다른 CMD에서 실행합니다.

```cmd
npm run start --workspace=@octv/mobile -- --web --lan
```

이전 CMD에 `set EXPO_PUBLIC_API_BASE_URL=...` 값이 남아 있으면 파일보다 우선할 수 있으므로 현재 주소로 맞추거나 새 CMD에서 실행합니다. IP가 바뀌면 두 주소 설정도 갱신합니다.

## 확인 순서

- [ ] 휴대폰 페이지의 실제 Origin이 허용 목록과 일치하는지 확인한다.
- [ ] 로그인 사전 요청 `OPTIONS /api/auth/login`의 200과 허용 Origin 헤더를 확인한다.
- [ ] 실제 로그인 `POST /api/auth/login`의 200을 확인한다.
- [ ] 같은 로그인으로 `GET /api/auth/me`의 200을 확인한다.
- [ ] 소속 기관 계정으로 모바일 사건 목록을 연다.

`/health`는 서버 접속만 확인합니다. 401·403·500 등은 CORS 이후 별도 원인을 확인하며 JWT·로그인 내부를 임의 수정하지 않습니다. 허용하지 않은 Origin의 사전 요청은 400입니다. CORS는 브라우저의 응답 접근 정책이며 인증이나 네트워크 방화벽을 대신하지 않습니다.

## 변경 검증

```cmd
.venv\Scripts\python -m unittest tests.test_cors tests.test_hazard_contract tests.test_langgraph_core
node --test tests/test_hazard_labels.mjs
npm run typecheck
```

CORS 검사의 DB는 Mock입니다. 실제 로그인·Android 설치 앱·FCM 수신은 각자 환경에서 별도로 확인합니다. 패키지·DB 스키마 변경은 없습니다.
