# 공통 목업·타입

`src/fixtures.json`은 준비된 UI 스냅샷이다. 값 변경·합산·추천·경로 계산을 하는 서비스는 없다.
`src/index.ts`는 JSON에서 타입을 내보내고, 선택한 ID의 고정 상세를 찾는 읽기 전용 도우미만 제공한다.

| 키 | 의미 |
|---|---|
| incidents / cctvs | 동일 사건·카메라의 공통 정보 |
| agencies / recommendations | 기관 ID와 사건별 추천 목록 |
| routes | `사건ID\|기관ID`별 A/B/C 후보. 기관마다 별도 값 |
| webRows / mobileIds / targetIds | 각 화면에 처음부터 표시할 고정 ID 목록 |
| stats / uiSnapshot | 이미 준비한 수치·비율·헤더·상태·표시 문구 |
| profile / support / notificationIds | 가상 프로필·요청 예시·사건 전달 알림 |
| mapPaths | 실제 지리와 무관한 SVG 도식 좌표 |

DB와의 대응: statusCode는 ERD의 DETECTED/CONFIRMED/SENT, CCTV connected는 CONNECTED/DISCONNECTED 표시 대응이다.
`SEL-*`, `CCTV-*`, `AG-*`는 화면 식별자이며 DB의 BIGINT PK가 아니다.
confidence는 표시용 %이고 DB는 DECIMAL이다. riskLabel·이유·분 단위 시간·지도 위치는 화면 전용 값이다.
목업 날짜와 인물은 샘플이며 실제 운영·인증 정보가 아니다. dropdown 옵션은 독립적인 표시 예시로 연동 필터링하지 않는다.
