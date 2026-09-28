-- 공통 상태 값. OFF는 cctvs.is_monitored = FALSE로 표현합니다.
CREATE TYPE agency_type_enum AS ENUM ('FIRE', 'POLICE', 'ROAD_MANAGEMENT', 'LOCAL_GOVERNMENT');
CREATE TYPE user_role_enum AS ENUM ('CONTROL_ADMIN', 'AGENCY_STAFF', 'RESPONDER');
CREATE TYPE connection_status_enum AS ENUM ('CONNECTED', 'DISCONNECTED', 'RECONNECTING');
CREATE TYPE video_quality_enum AS ENUM ('GOOD', 'LOW', 'UNAVAILABLE');
CREATE TYPE analysis_status_enum AS ENUM ('RUNNING', 'STOPPED', 'ERROR');
CREATE TYPE monitored_mode_enum AS ENUM ('BASE', 'ALERT', 'POST_ALERT', 'VERIFY');
CREATE TYPE incident_status_enum AS ENUM ('DETECTED', 'FALSE_POSITIVE', 'CONFIRMED', 'SENT');
CREATE TYPE weather_status_enum AS ENUM ('ACTIVE', 'ENDED');
CREATE TYPE recommendation_status_enum AS ENUM ('RECOMMENDED', 'DELIVERED');
CREATE TYPE support_type_enum AS ENUM ('PERSONNEL', 'EQUIPMENT', 'TRAFFIC_CONTROL', 'OTHER');
