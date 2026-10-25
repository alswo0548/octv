# 웹 통합 수정 실행 안내 (2026-10-25)

이 변경은 배포 완료가 아닙니다. 실제 DB·Runtime·외부 API·모바일 통합 시연은 실행 PC에서 확인해야 합니다.

## 먼저 확인

- `backend/.env`의 `OCTV_YOLO_MODEL_PATH`에 기존 승인 **운영 CCTV 모델** 경로를 지정합니다. 비어 있으면 v5 Runtime이 시작을 거부합니다. Demo 모델로 UTIC를 임의 대체하던 fallback을 제거했습니다.
- 기존 `OCTV_DEMO_ENABLED=1`, `OCTV_DECISION_ENABLED=1`, Redis 및 외부 API 설정을 유지합니다. 키를 Git에 올리지 않습니다.
- API는 아래 v5 실행기를 사용합니다. 일반 `uvicorn backend.app.main:app`에는 v5 미디어·추론 프레임·시연 목록 정리 API가 없습니다.
- 기존 CCTV Runtime과 v5 Runtime을 동시에 실행하지 않습니다.

## Windows CMD — 각 실행 창에서 프로젝트 폴더 기준

최초 의존성/빌드 확인:
```bat
npm ci
npm run typecheck
npm run build:web
.venv\Scripts\python -m scripts.check_predeploy_readonly
```

Docker:
```bat
docker compose up -d db redis mediamtx
```

FastAPI (일반 uvicorn과 동시에 실행하지 않음):
```bat
.venv\Scripts\python -m scripts.run_demo_api_v5 --host 0.0.0.0 --port 8000
```

Celery (Windows):
```bat
.venv\Scripts\python -m celery -A backend.app.workers:celery_app worker --pool=solo --loglevel=info
```

CCTV Runtime:
```bat
.venv\Scripts\python -m scripts.run_cctv_runtime_v5
```

웹 / 모바일 웹 (서로 다른 창):
```bat
npm run dev:web
npm run dev:mobile:web
```

진단 / 회귀 검사:
```bat
.venv\Scripts\python -m scripts.check_predeploy_readonly
.venv\Scripts\python -m scripts.check_demo_v5_live
.venv\Scripts\python -m unittest tests.test_predeploy_v5_sessions tests.test_predeploy_preview tests.test_predeploy_v5_api tests.test_demo_v5_model_router tests.demo.test_demo_traffic_overlay -v
node --test tests/predeploy_web.test.mjs tests/web_delivery.test.mjs tests/mobile_notifications.test.mjs
```

## 변경의 범위와 제한

- 지도는 기존 OpenStreetMap 유지. 기존 핀 모양·파동 스타일을 실제 좌표 지도에 연결하고 P1/P2/P3 색상·드래그·휠·전체보기를 추가했습니다. 위성지도는 적용하지 않았습니다.
- 사건번호는 표시용 `OCTV_P2_12_tree` 형식이며 숫자는 DB 사건 ID입니다. 내부 UUID/API 참조는 그대로입니다. 우선순위 미분석은 `대기`로 표시합니다.
- 관리자의 사건 삭제는 **현재 로그인 세션의 웹 목록 숨김**입니다. 원본 DB·모바일·기관·경로·알림 이력은 보존합니다. 로그인 갱신이나 복원 버튼으로 복원됩니다. 영구 소프트 삭제가 아닙니다.
- 종료된 승인 Demo 3대의 사건은 웹 목록·지도에서 제외됩니다. 과거 Demo 사건도 보관 대상으로 숨깁니다. 통계는 DB 이력을 계속 집계합니다. 직접 상세 조회와 기존 모바일 알림 이력은 유지합니다.
- v5 어댑터만 Demo 시작시각별 시간 검증 인스턴스와 dedup 키를 분리합니다. 실제 추론·기존 시간 검증을 거친 신규 사건만 저장합니다. UTIC는 기존 Pipeline으로 위임합니다.
- 실제 YOLO 프레임과 박스는 Redis 30초 TTL의 별도 정지 화면으로 제공합니다. MP4 위에 시각이 맞지 않는 박스를 덧씌우지 않습니다. 프레임 미수신·API 오류를 정상으로 표시하지 않습니다.
- 기관 추천 조회 버튼은 DETECTED에서도 열 수 있지만, 실제 전달은 기존의 사건 확인·권한·중복 방지 조건을 유지합니다.
- LLM 호출은 미구현입니다. 저장된 점수·누락 여부를 이용한 규칙 기반 안내라고 표시하고 원본 상세 근거를 보존합니다.
- 신규 사건 알림은 관리자 로그인 기간 동안 페이지 이동 후에도 유지되며, 로그아웃 시 분리됩니다. FCM은 변경하지 않습니다.
- 웹 목록 필터 정확성을 위해 관리자는 사건 API 전체 페이지를 읽어 숨김 후 페이지를 나눕니다. 발표용 데이터 규모에 적합하며 대규모 운영 시 서버측 보관/페이지네이션 설계가 필요합니다.

## 실기기 검수

- [ ] 운영 모델 경로를 확인한다.
- [ ] API·Celery·v5 Runtime을 각각 실행한다.
- [ ] 시연 시작 후 실제 추론 프레임과 신규 사건번호를 확인한다.
- [ ] 분석 완료 후 위험도·우선순위·추천 기관·경로를 확인한다.
- [ ] 사건 확인 후 기관을 선택해 전달한다.
- [ ] 해당 기관 모바일 알림을 확인한다.
- [ ] 시연 종료 후 웹 목록에서 Demo 사건이 제외되는지 확인한다.
- [ ] 재시작 후 새로운 DB 사건 ID가 생성되는지 확인한다.
- [ ] UTIC 감시·사건·전달 이력이 유지되는지 확인한다.
- [ ] 테스트 CCTV 2대의 정확한 식별자와 참조를 확인한 뒤 비활성화한다.
