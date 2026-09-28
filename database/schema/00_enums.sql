-- ENUM은 테이블보다 먼저 생성합니다. schema.sql에서 이 파일을 가장 먼저 실행합니다.
-- 값 변경 시 기존 DB용 migrations SQL도 함께 작성하세요.

-- 기관 유형
CREATE TYPE agency_type_enum AS ENUM (
    'FIRE',
    'POLICE',
    'ROAD_MANAGEMENT',
    'LOCAL_GOVERNMENT'
);

-- 사용자 내부 역할 (화면 명칭과 구분)
CREATE TYPE user_role_enum AS ENUM (
    'CONTROL_ADMIN',
    'AGENCY_STAFF',
    'RESPONDER'
);

-- CCTV 연결 상태
CREATE TYPE connection_status_enum AS ENUM (
    'CONNECTED',
    'DISCONNECTED',
    'RECONNECTING'
);

-- 영상 품질
CREATE TYPE video_quality_enum AS ENUM (
    'GOOD',
    'LOW',
    'UNAVAILABLE'
);

-- 분석 프로세스 상태
CREATE TYPE analysis_status_enum AS ENUM (
    'RUNNING',
    'STOPPED',
    'ERROR'
);

-- ON 상태에서의 감시 모드 (OFF는 is_monitored=false)
CREATE TYPE monitored_mode_enum AS ENUM (
    'BASE',
    'ALERT',
    'POST_ALERT',
    'VERIFY'
);

-- 사건 처리 상태
CREATE TYPE incident_status_enum AS ENUM (
    'DETECTED',
    'FALSE_POSITIVE',
    'CONFIRMED',
    'SENT'
);

-- 기상특보 상태
CREATE TYPE weather_status_enum AS ENUM (
    'ACTIVE',
    'ENDED'
);

-- 기관 추천/전달 상태
CREATE TYPE recommendation_status_enum AS ENUM (
    'RECOMMENDED',
    'DELIVERED'
);

-- 추가 지원요청 유형
CREATE TYPE support_type_enum AS ENUM (
    'PERSONNEL',
    'EQUIPMENT',
    'TRAFFIC_CONTROL',
    'OTHER'
);
