# OCTV 시연 v5 연결 패치 (보호 우선)

## 하는 일
- 기존 `ai/detection/*`, `backend/app/demo/*`, 로그인/회원가입/VERIFY/Incident, DB 스키마를 **수정하지 않습니다**.
- 기존 FastAPI Demo start/stop 관리자 API를 웹 모니터링의 '시연 시작/종료' 버튼에 연결합니다.
- DEMO-N001/N002/N003만 승인된 N052 S2 / Cycle7 / L_last 모델로 YOLO 추론하도록 신규 Runtime 진입점에서 분기합니다.
- UTIC 3대는 동일 Runtime에서 기본 운영 탐지를 유지합니다. 기본 모델 경로가 비어 있으면 **임시** Cycle7을 사용하므로 실제 CCTV에서 오탐이 없는지 반드시 검사해야 합니다.
- DEMO MP4 재생은 별도 웹 표시 전용 경로를 사용합니다. 영상이 재생된다는 사실과 사건이 만들어졌다는 사실은 다릅니다.
- 관리자만 재생 티켓을 발급하며, 15분짜리 임시 링크로 MP4를 브라우저 `<video>`에서 재생합니다. **공개 인터넷에 그대로 노출하지 말고 시연용 로컬/LAN에서만 사용**하세요.
- Demo 시작: 기상특보/감시 모드만 변경. 가짜 YOLO 탐지나 Incident는 만들지 않습니다.

## 실제 변경
신규: `ai/demo_v5/*`, `backend/app/demo_v5_media/*`, `scripts/run_demo_api_v5.py`, `scripts/run_cctv_runtime_v5.py`, `frontend/web/src/components/DemoV5Controls.tsx`, `frontend/web/src/components/DemoV5Video.tsx`, `tests/test_demo_v5_model_router.py`
한 곳만 소규모 수정: `frontend/web/src/pages/MonitorPage.tsx` (시연 버튼과 Demo 전용 뷰어 연결)
설정: 기존 키 유지하며 `backend/.env`에 Demo 3개 변수만 추가/갱신. `OCTV_YOLO_MODEL_PATH`는 그대로 보존.

## 주의
v5 승인 HTML의 1초/80% 시각적 시간 검증은 기존 OCTV Runtime의 3회/15초 VERIFY와 다릅니다. 이 패치는 웹 검수 결과와 동일한 사건화 결과를 보장하지 않습니다. 데모 대상 클래스/시작 threshold만 사용합니다. N052 `keep_conf=0.50` 유지 정책은 현 OCTV Runtime의 샘플링 주기에서 **재현하지 않습니다**. 이 점은 사용자 승인 설정 중 아직 미연결된 부분이며, 실제 Incident 3건 검증 후 필요하면 팀원과 협의해야 합니다.

## 적용
1. `main`에서 분기한 `feat/demo-v5-model-routing` 확인 및 `git status --short` 공백.
2. 프로젝트 루트 CMD에서 (Downloads에 설치 도구 다운로드한 경우):
   `.venv\Scripts\python "%USERPROFILE%\Downloads\OCTV_v5_통합설치_20261023.py" --check`
3. 계획 결과가 정상이라면:
   `.venv\Scripts\python "%USERPROFILE%\Downloads\OCTV_v5_통합설치_20261023.py" --apply`
4. `git status --short`에서 추가 파일/MonitorPage 변경만 확인.
5. 데이터 변동 없는 단위 테스트:
   `.venv\Scripts\python -m unittest discover -s tests -p test_demo_v5_model_router.py -v`
6. 기존 API/Runtime이 떠 있다면 먼저 각각 정상 종료. **같은 DB에 CCTV Runtime 두 개 동시 실행 금지.**
7. 백엔드 API 터미널: `.venv\Scripts\python -m scripts.run_demo_api_v5 --host 0.0.0.0 --port 8000`
8. 별도 Runtime 터미널: `.venv\Scripts\python -m scripts.run_cctv_runtime_v5`
9. 기존 웹 실행방식으로 `frontend/web` 실행. `CONTROL_ADMIN` 계정으로 로그인 → CCTV 모니터링 → 시연 시작 → Demo CCTV 클릭 후 영상/YOLO 로그/Incident 확인.
10. 종료 후 시연 종료 버튼. 실제 UTIC CCTV는 BASE 유지 확인.

## 미완료 작업 (반드시 확인)
- USER PC에서 실제 API/Runtime/웹/추론/VERIFY/Incident 3건/관할·경로·FCM 통합 테스트 **미실행**.
- DEMO 동시 3대와 UTIC 3대의 성능 부하/오탐 미검증. GPU 없는 CPU에선 처리량 낮을 수 있음.
- Demo MP4는 긴 영상(특히 N001 약 115 MB); 로컬/LAN 재생 권장.
- UI는 기존 CCTV 목록에서 카메라를 선택하여 보여주며 3분할 월(wall)은 구현하지 않음.
- 기존 정상 CCTV 모델은 미설정이어서 임시 Cycle7 적용; 선택된 완성 운영 모델이 있다면 `OCTV_YOLO_MODEL_PATH`에 명시하고 추론·오탐 검증.
- 이 패치는 새 실행 진입점이므로 배포 시 명령도 신규 진입점으로 변경해야 함.
