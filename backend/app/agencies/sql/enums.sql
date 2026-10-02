-- 최신 첨부 ERD 기준. 기존 DB에는 migrations를 적용합니다.
CREATE TYPE agency_type_enum AS ENUM ('FIRE', 'POLICE', 'ROAD_MANAGEMENT', 'LOCAL_GOVERNMENT');
CREATE TYPE recommendation_status_enum AS ENUM ('RECOMMENDED', 'DELIVERED', 'COMPLETED');
