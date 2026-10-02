-- 기존 첨부 코드의 14개 테이블 DB -> 최신 첨부 ERD의 13개 테이블 DB.
-- 실행: python scripts/db.py migrate (먼저 전체 논리 백업을 저장합니다).
-- FALSE_POSITIVE 행은 임의 변환하지 않고 중단합니다. 처리 정책 합의가 먼저입니다.
\set ON_ERROR_STOP on
\if :{?backup_confirmed}
\else
  \echo 'STOP: Run python scripts/db.py migrate to create a backup first.'
  \quit 3
\endif
BEGIN;
SET LOCAL search_path TO public;
SET LOCAL lock_timeout = '5s';
DO $$
BEGIN
    IF to_regclass('public.route_evaluations') IS NULL THEN
        RAISE EXCEPTION 'Expected old 14-table schema. Already migrated or unsupported schema; no changes applied.';
    END IF;
    IF (SELECT array_agg(column_name::text ORDER BY ordinal_position)
        FROM information_schema.columns WHERE table_schema='public' AND table_name='route_evaluations')
        <> ARRAY['id','rule_version','created_at','agency_recommendation_id'] THEN
        RAISE EXCEPTION 'Custom route_evaluations columns found; review manually before migration.';
    END IF;
END $$;
LOCK TABLE incidents, agencies, cctvs, weather_alerts, incident_contexts,
    incident_agency_recommendations, route_evaluations, route_candidates, notifications
    IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM incidents WHERE status::text = 'FALSE_POSITIVE') THEN
        RAISE EXCEPTION 'FALSE_POSITIVE data exists. Latest ERD has no equivalent. Decide its handling; do not auto-convert/delete.';
    END IF;
    IF EXISTS (SELECT 1 FROM incidents WHERE status::text NOT IN ('DETECTED','CONFIRMED','SENT','RESOLVED')) THEN
        RAISE EXCEPTION 'Unknown incident state. Manual review required.';
    END IF;
    IF EXISTS (SELECT 1 FROM cctvs WHERE monitored_mode::text NOT IN ('BASE','ALERT','VERIFY','POST_ALERT','OFF')) THEN
        RAISE EXCEPTION 'Unknown monitored mode. Manual review required.';
    END IF;
    IF EXISTS (
      SELECT 1 FROM notifications n
      JOIN route_evaluations e ON e.id=n.route_evaluation_id
      JOIN incident_agency_recommendations r ON r.id=e.agency_recommendation_id
      WHERE n.incidents_id<>r.incident_id OR n.agency_id<>r.agency_id
    ) THEN
        RAISE EXCEPTION 'Notification and recommendation incident/agency mismatch. Review data first.';
    END IF;
END $$;
-- Recreate enum types transactionally, preserving every permitted stored value.
ALTER TABLE incidents ALTER COLUMN status DROP DEFAULT;
ALTER TYPE incident_status_enum RENAME TO incident_status_enum_old;
CREATE TYPE incident_status_enum AS ENUM ('DETECTED','CONFIRMED','SENT','RESOLVED');
ALTER TABLE incidents ALTER COLUMN status TYPE incident_status_enum USING status::text::incident_status_enum;
ALTER TABLE incidents ALTER COLUMN status SET DEFAULT 'DETECTED';
DROP TYPE incident_status_enum_old;
ALTER TYPE monitored_mode_enum RENAME TO monitored_mode_enum_old;
CREATE TYPE monitored_mode_enum AS ENUM ('BASE','ALERT','VERIFY','POST_ALERT','OFF');
ALTER TABLE cctvs ALTER COLUMN monitored_mode TYPE monitored_mode_enum USING monitored_mode::text::monitored_mode_enum;
DROP TYPE monitored_mode_enum_old;
-- Migrate relationships and metadata before removing old references.
ALTER TABLE route_candidates
    ADD COLUMN rule_version VARCHAR(50),
    ADD COLUMN created_at TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN agency_recommendation_id BIGINT REFERENCES incident_agency_recommendations(id);
UPDATE route_candidates c SET rule_version=e.rule_version, created_at=e.created_at,
    agency_recommendation_id=e.agency_recommendation_id
FROM route_evaluations e WHERE c.route_evaluation_id=e.id;
ALTER TABLE route_candidates
    ALTER COLUMN rule_version SET NOT NULL,
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN agency_recommendation_id SET NOT NULL,
    ALTER COLUMN score_breakdown_json DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN agency_recommendation_id BIGINT REFERENCES incident_agency_recommendations(id);
UPDATE notifications n SET agency_recommendation_id=e.agency_recommendation_id
FROM route_evaluations e WHERE n.route_evaluation_id=e.id;
ALTER TABLE notifications ALTER COLUMN agency_recommendation_id SET NOT NULL;
-- Removed ERD fields remain recoverable in the external backup made before this transaction.
ALTER TABLE route_candidates DROP COLUMN route_evaluation_id,
    DROP COLUMN traffic_score, DROP COLUMN control_score, DROP COLUMN hazard_score,
    DROP COLUMN accessibility_score, DROP COLUMN distance_score;
ALTER TABLE notifications DROP COLUMN route_evaluation_id;
DROP TABLE route_evaluations;
ALTER TABLE incidents DROP COLUMN detection_duration_sec;
ALTER TABLE weather_alerts DROP COLUMN raw_data_json;
ALTER TABLE incident_contexts DROP COLUMN raw_context_json;
ALTER TABLE incident_contexts ALTER COLUMN captured_at DROP NOT NULL;
ALTER TABLE incident_agency_recommendations DROP COLUMN recommended_at;
ALTER TABLE agencies ALTER COLUMN phone DROP NOT NULL;
COMMENT ON COLUMN route_candidates.rule_version IS '규칙 버전';
COMMENT ON COLUMN route_candidates.created_at IS '생성 일시';
COMMENT ON COLUMN route_candidates.agency_recommendation_id IS '기관 추천 ID';
COMMENT ON COLUMN notifications.agency_recommendation_id IS '기관 추천 ID';
COMMENT ON COLUMN incident_agency_recommendations.agency_id IS '기관 ID · 최신 ERD BIGIBT 오기를 BIGINT로 수정';
-- Verification runs before COMMIT. Any mismatch rolls back the complete change.
\ir 002_contract.sql
COMMIT;
