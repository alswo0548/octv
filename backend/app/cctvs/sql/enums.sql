-- 최신 첨부 ERD 기준. 기존 DB에는 migrations를 적용합니다.
CREATE TYPE connection_status_enum AS ENUM ('CONNECTED', 'DISCONNECTED', 'RECONNECTING');
CREATE TYPE video_quality_enum AS ENUM ('GOOD', 'LOW', 'UNAVAILABLE');
CREATE TYPE analysis_status_enum AS ENUM ('RUNNING', 'STOPPED', 'ERROR');
CREATE TYPE monitored_mode_enum AS ENUM ('BASE', 'ALERT', 'VERIFY', 'POST_ALERT', 'OFF');
CREATE TYPE weather_status_enum AS ENUM ('ACTIVE', 'ENDED');
