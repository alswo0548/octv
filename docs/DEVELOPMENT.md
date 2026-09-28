# 개발 기준

## 확정된 역할과 범위

- WEB: 119 상황실의 관제·사건 확인·기관 및 경로 추천·선택한 기관에 정보 전달.
- MOBILE: **현장 담당자**의 전달받은 사건·영상·경로 확인, **추가 지원요청**.
- 출동 결정·인원 배정·최종 지령·대응완료 보고·사건 종결은 기관의 기존 체계에서 처리합니다.
- 알림 종류는 **사건 전달**입니다. 제외된 경로도 조회할 수 있지만 네비게이션은 사용할 수 없습니다.
- 기관 탭은 조회 대상을 바꾸고, 체크박스는 전달 대상을 고릅니다. 기관별 후보 경로는 3개입니다.
- 화면 역할 명칭과 DB 역할 값(`CONTROL_ADMIN`, `AGENCY_STAFF`, `RESPONDER`)은 별개입니다.

## CCTV 감시 정책

연결 상태(`CONNECTED` 등)와 감시 상태는 별개입니다.

| 화면 상태 | 표시 | DB 표현 |
|---|---|---|
| BASE | ON | is_monitored=true, monitored_mode=BASE |
| OFF | OFF | is_monitored=false; 모드 해석은 하지 않음 |
| ALERT | ON · 특보 감시 중 | true, ALERT |
| POST_ALERT | ON · 해제 후 확인 대기 | true, POST_ALERT |
| VERIFY | ON · 집중 검증 중 | true, VERIFY |

특보 발령 → 대상 ON. 특보 중 OFF 시도 → 거절하고 ON 유지.
특보 해제 → POST_ALERT로 ON 유지. 관리자가 상황을 확인한 뒤 수동 OFF.
시간 경과·AI 판단으로 자동 OFF하지 않습니다. 이 규칙은 나중에 서버에서도 검사해야 합니다.

팝업 제목: **감시 중지 불가** / 버튼: **확인**

> 특보 발령 중인 CCTV는 감시를 중지할 수 없습니다. 특보 해제 후 관리자가 상황을 확인한 뒤 비활성화할 수 있습니다.

## UI 연결 시 지킬 것

- 현재 로그인·회원가입·이메일 확인·필터·기관 전달·저장 등은 목업입니다. 실제 조회/전송 성공으로 처리하지 않습니다.
- `shared/src/fixtures.json`은 화면 샘플입니다. 문자열 ID(`SEL-001` 등)와 표시용 %를 DB BIGINT ID·0~1 confidence로 그대로 저장하지 않습니다.
- OCTV 로고·영문, 영상 배경·기존 디자인을 유지합니다. 영상은 창 비율에 맞게 cover로 채웁니다.
- W04 왼쪽 CCTV 목록은 오른쪽 카드 하단까지 채웁니다. 오른쪽 선택 CCTV/분석 카드는 내부 스크롤 없이 펼칩니다.
- 각 CCTV 영상·이미지에 `경찰청(UTIC) 제공`을 표시합니다. 지도·장식용 배경에는 붙이지 않습니다.

## 구현 순서

1. DB 생성 확인 → `backend/app/db/session.py` 연결과 `config.py` 환경설정.
2. 인증/권한과 DB 제약 합의 → 사용자·기관·CCTV 조회.
3. 사건/필터/상세·설정·통계 → 프론트의 해당 목업을 한 화면씩 API로 교체.
4. AI: 영상/품질 → 탐지 → 시간 검증/중복 판별 → 사건 등록 → 상황 수집 → 위험도·기관·경로 평가.
5. 기관 전달·알림·추가 지원요청 → 실패/중복 전송/권한 검사.

`router.py`는 URL, `schemas.py`는 입출력 초안, `service.py`는 처리 규칙, `repository.py`는 SQL입니다.
각 파일의 TODO를 구현하며 API 계약을 확정합니다. 현재 URL/스키마 초안이 완성된 업무 사양은 아닙니다.
Python 직접 의존성은 각 requirements에 버전을 고정했습니다. AI는 CPU 개발 기준이며 GPU는 장비별 검증이 필요합니다.
실제 모델·추천 규칙·학습 자료는 아직 없습니다. LLM 어댑터는 `langchain-openai`를 준비했으며 제공자를 바꾸면 의존성도 함께 바꿉니다.
골격 검사는 `tests/test_backend.py`에 있습니다. 기능을 구현하면 해당 501 기대값을 실제 기능 테스트로 교체합니다.

## 화면 설계 링크

- [WEB 한 장 흐름도](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=a5ac146a-5787-80fa-8008-b54bd425b7c3&page-id=a5ac146a-5787-80fa-8008-b54bd425b7c4)
- [MOBILE 한 장 흐름도](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=a5ac146a-5787-80fa-8008-b54bd425b7c3&page-id=415d8a39-8f21-80a0-8008-b54cf69488fb)
- [WEB 상세 스토리보드](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4cdadf8b0be)
- [MOBILE 상세 스토리보드](https://design.penpot.app/#/workspace?team-id=d8ac01df-6646-81d2-8008-ac44f628bb56&file-id=d8ac01df-6646-81d2-8008-ac4abdee3ed7&page-id=51c1e37d-020a-80ac-8008-b4d39671b27f)

화면 목록/이동 키는 `shared/src/index.ts`, WEB `App.tsx`, MOBILE `App.tsx`와 `navigation/types.ts`에서 확인합니다.
