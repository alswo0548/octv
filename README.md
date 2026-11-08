<div align="center">

# OCTV

**AI 기반 CCTV 도로 재난 탐지·대응 의사결정 지원 시스템**

CCTV에서 탐지한 도로 재난을 사건으로 관리하고, 기상·수위·교통 등 외부 정보를 함께 분석해 **위험도·대응 우선순위·담당 기관·이동 경로**를 추천합니다.

[실제 기능 시연](https://alswo0548.github.io/minjae-portfolio/octv.html) · [기획·설계·개발 과정 (Notion)](https://app.notion.com/p/99ac34c55d37838bae8f81588467f52f) · [핵심 구현 코드](https://github.com/alswo0548/minjae-portfolio/blob/main/projects/01-octv/TECHNICAL.md)

</div>

## 주요 화면

| CCTV 재난 탐지 | 사건 모니터링 |
|:---:|:---:|
| ![침수 CCTV 탐지 화면](https://raw.githubusercontent.com/alswo0548/minjae-portfolio/main/assets/01-octv/demo_cctv.jpg) | ![사건 목록과 상세 화면](https://raw.githubusercontent.com/alswo0548/minjae-portfolio/main/assets/01-octv/demo_overview.jpg) |
| **위험도·우선순위 분석** | **대응 기관·경로 추천** |
| ![외부 상황 및 위험도 분석 화면](https://raw.githubusercontent.com/alswo0548/minjae-portfolio/main/assets/01-octv/demo_analysis.jpg) | ![대응 기관 및 이동 경로 비교 화면](https://raw.githubusercontent.com/alswo0548/minjae-portfolio/main/assets/01-octv/demo_routes.jpg) |

영상으로 확인하려면 **[OCTV 포트폴리오의 자동재생 시연](https://alswo0548.github.io/minjae-portfolio/octv.html)**을 참고하세요.

## 주요 기능

| 기능 | 설명 |
|---|---|
| **CCTV 탐지·사건화** | YOLO 기반 재난 후보를 시간 검증 후 사건으로 생성·관리 |
| **사건 모니터링** | 사건 목록·지도·상세 화면에서 탐지 결과와 처리 상태 확인 |
| **외부 정보 연동** | 기상·수위·교통 정보를 수집하고 누락·검증 상태를 구분 |
| **위험도·우선순위** | 외부 맥락과 규칙 기반 점수로 P1·P2·P3 우선순위 판단 |
| **기관·경로 추천** | 기관의 역할·관할·접근성과 후보 경로의 시간·거리 비교 |
| **기관 전달·알림** | 관제 담당자의 기관 전달과 Celery·Redis 기반 비동기 처리, FCM 발송 연동 |

탐지된 사건을 분석해 대응 선택을 **지원**하는 서비스입니다. 실제 출동 지령이나 현장 대응 완료를 자동으로 수행하지는 않습니다.

## 기술 구성

- **AI·판단:** Python · YOLO · OpenCV · LangGraph · MCP · Rule 기반 위험도·추천
- **Backend·데이터:** FastAPI · PostgreSQL · Redis · Celery
- **Web·Mobile:** React · TypeScript · Vite · React Native · Expo
- **영상·알림:** MediaMTX · WebRTC · Firebase Admin SDK · FCM
- **인프라:** Docker Compose · Caddy · DigitalOcean

사건 조회 → 외부 상황 수집 → 위험도 판단 → 기관 선정 → 경로 평가 → 결과 저장을 연결하며, 분석과 알림 작업을 비동기로 분리했습니다.

## 담당 역할

**슬기로운 출동생활 · 2인 팀 (KDT 최종 프로젝트)**

| 팀원 | 주요 담당 |
|---|---|
| **이민재 (팀장)** · [@alswo0548](https://github.com/alswo0548) | 사건 저장·조회, 판단·대응 백엔드, 외부 정보 연동, 위험도·기관·경로 추천, Celery·Redis·FCM, 통합·배포, CCTV 환경 적응학습 |
| **박수연** | YOLO 탐지·시간 검증·사건화, 탐지 모델 Baseline·Branch A 및 데이터 처리 |

탐지·사건화와 판단·대응의 담당 범위를 구분했습니다. 최종 서비스의 연동·검증은 협업으로 진행했습니다.

## 로컬에서 화면 확인

Node.js 24 · npm 11 기준으로 웹 개발 화면을 실행할 수 있습니다.

```bash
npm ci
npm run dev:web
```

전체 시스템의 분석·DB·영상·알림 기능은 별도 환경 변수와 PostgreSQL·Redis·영상 중계·외부 API 설정 등이 필요합니다. 운영 구성은 [배포 Compose](deploy/compose.prod.yaml), [환경 설정 예시](deploy/production.env.example)를 참고하세요.

```text
ai/         탐지·외부 맥락·위험도·기관 추천·분석 파이프라인
backend/    FastAPI·사건·기관·알림·비동기 작업
frontend/   관제 웹·모바일 화면
database/   PostgreSQL 스키마 및 마이그레이션
deploy/     운영 컨테이너·프록시 설정
tests/      자동화 테스트
```

기획서, 시스템 아키텍처, ERD, API 명세, 문제 해결 과정은 [**Notion 프로젝트 문서**](https://app.notion.com/p/99ac34c55d37838bae8f81588467f52f)에 정리했습니다.
