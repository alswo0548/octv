-- 최신 첨부 ERD 기준. 기존 DB에는 migrations를 적용합니다.
CREATE TYPE user_role_enum AS ENUM ('CONTROL_ADMIN', 'AGENCY_STAFF', 'RESPONDER');
