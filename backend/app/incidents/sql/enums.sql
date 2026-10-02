-- 최신 첨부 ERD 기준. 기존 DB에는 migrations를 적용합니다.
CREATE TYPE incident_status_enum AS ENUM ('DETECTED', 'CONFIRMED', 'SENT', 'RESOLVED', 'FALSE_POSITIVE');
