-- 14-table original OR previously delivered 13-table database -> corrected final ERD.
-- Always run with python scripts/db.py migrate (verified pg_dump backup first).
\set ON_ERROR_STOP on
\if :{?backup_confirmed}
  \if :backup_confirmed
  \else
    DO $$ BEGIN RAISE EXCEPTION 'STOP: Run python scripts/db.py migrate to create a backup first.'; END $$;
  \endif
\else
  DO $$ BEGIN RAISE EXCEPTION 'STOP: Run python scripts/db.py migrate to create a backup first.'; END $$;
\endif
BEGIN;
SET LOCAL search_path TO public;
SET LOCAL lock_timeout = '5s';
LOCK TABLE region, agencies, users, cctvs, monitoring_settings, incidents,
    weather_alerts, incident_contexts, incident_assessments,
    incident_agency_recommendations, route_candidates, notifications,
    incident_support_requests IN ACCESS EXCLUSIVE MODE;
DO $migrate$
DECLARE missing_capture_ids BIGINT[];
BEGIN
    SELECT array_agg(id ORDER BY id) INTO missing_capture_ids FROM incident_contexts WHERE captured_at IS NULL;
    IF missing_capture_ids IS NOT NULL THEN
        RAISE EXCEPTION 'incident_contexts.captured_at contains NULL: IDs %. Restore the actual capture time; no timestamp was invented.', missing_capture_ids;
    END IF;
    IF EXISTS (SELECT 1 FROM incidents WHERE status::text NOT IN ('DETECTED','CONFIRMED','SENT','RESOLVED','FALSE_POSITIVE')) THEN
        RAISE EXCEPTION 'Unknown incident status; review before migration.';
    END IF;
    IF EXISTS (SELECT 1 FROM incident_agency_recommendations WHERE recommendation_status::text NOT IN ('RECOMMENDED','DELIVERED','COMPLETED')) THEN
        RAISE EXCEPTION 'Unknown recommendation status; review before migration.';
    END IF;
    IF to_regclass('public.route_evaluations') IS NOT NULL THEN
        LOCK TABLE route_evaluations IN ACCESS EXCLUSIVE MODE;
        IF (SELECT array_agg(column_name::text ORDER BY ordinal_position)
            FROM information_schema.columns WHERE table_schema='public' AND table_name='route_evaluations')
            <> ARRAY['id','rule_version','created_at','agency_recommendation_id'] THEN
            RAISE EXCEPTION 'Custom route_evaluations columns found; review before migration.';
        END IF;
        IF EXISTS (
            SELECT 1 FROM notifications n JOIN route_evaluations e ON e.id=n.route_evaluation_id
            JOIN incident_agency_recommendations r ON r.id=e.agency_recommendation_id
            WHERE n.incidents_id<>r.incident_id OR n.agency_id<>r.agency_id
        ) THEN RAISE EXCEPTION 'Notification incident/agency mismatch. Review data before migration.'; END IF;
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
ALTER TABLE incident_agency_recommendations DROP COLUMN recommended_at;
ALTER TABLE agencies ALTER COLUMN phone DROP NOT NULL;
COMMENT ON COLUMN route_candidates.rule_version IS '규칙 버전';
COMMENT ON COLUMN route_candidates.created_at IS '생성 일시';
COMMENT ON COLUMN route_candidates.agency_recommendation_id IS '기관 추천 ID';
COMMENT ON COLUMN notifications.agency_recommendation_id IS '기관 추천 ID';
COMMENT ON COLUMN incident_agency_recommendations.agency_id IS '기관 ID';

    END IF;
    -- Recreate ENUMs within the transaction so new values are usable immediately.
    -- Old FALSE_POSITIVE values remain FALSE_POSITIVE; no status remapping.
    ALTER TABLE incidents ALTER COLUMN status DROP DEFAULT;
    ALTER TYPE incident_status_enum RENAME TO incident_status_enum_before_003;
    CREATE TYPE incident_status_enum AS ENUM ('DETECTED','CONFIRMED','SENT','RESOLVED','FALSE_POSITIVE');
    ALTER TABLE incidents ALTER COLUMN status TYPE incident_status_enum USING status::text::incident_status_enum;
    ALTER TABLE incidents ALTER COLUMN status SET DEFAULT 'DETECTED';
    DROP TYPE incident_status_enum_before_003;
    ALTER TABLE incident_agency_recommendations ALTER COLUMN recommendation_status DROP DEFAULT;
    ALTER TYPE recommendation_status_enum RENAME TO recommendation_status_enum_before_003;
    CREATE TYPE recommendation_status_enum AS ENUM ('RECOMMENDED','DELIVERED','COMPLETED');
    ALTER TABLE incident_agency_recommendations ALTER COLUMN recommendation_status TYPE recommendation_status_enum
        USING recommendation_status::text::recommendation_status_enum;
    ALTER TABLE incident_agency_recommendations ALTER COLUMN recommendation_status SET DEFAULT 'RECOMMENDED';
    DROP TYPE recommendation_status_enum_before_003;
    ALTER TYPE monitored_mode_enum RENAME TO monitored_mode_enum_before_003;
    CREATE TYPE monitored_mode_enum AS ENUM ('BASE','ALERT','VERIFY','POST_ALERT','OFF');
    ALTER TABLE cctvs ALTER COLUMN monitored_mode TYPE monitored_mode_enum USING monitored_mode::text::monitored_mode_enum;
    DROP TYPE monitored_mode_enum_before_003;
    ALTER TABLE incident_contexts ALTER COLUMN captured_at SET NOT NULL;
    IF EXISTS (
        SELECT 1 FROM notifications n JOIN incident_agency_recommendations r ON r.id=n.agency_recommendation_id
        WHERE n.incidents_id<>r.incident_id OR n.agency_id<>r.agency_id
    ) THEN RAISE EXCEPTION 'Notification incident/agency mismatch. Review data before migration.'; END IF;
END $migrate$;
-- The preflight reports duplicate row IDs only; it never deletes or merges rows.
\ir 003_preflight.sql
ALTER TABLE cctvs ADD CONSTRAINT uq_cctvs_provider_external UNIQUE (provider, external_cctv_id);
ALTER TABLE incidents ADD CONSTRAINT uq_incidents_incident_no UNIQUE (incident_no);
ALTER TABLE weather_alerts ADD CONSTRAINT uq_weather_alerts_external_region UNIQUE (external_alert_id, region_code);
ALTER TABLE incident_agency_recommendations ADD CONSTRAINT uq_recommendations_incident_agency UNIQUE (incident_id, agency_id);
ALTER TABLE notifications ADD CONSTRAINT uq_notifications_recommendation_user UNIQUE (agency_recommendation_id, user_id);
CREATE UNIQUE INDEX uq_users_email_normalized ON users (lower(btrim(email)));
CREATE UNIQUE INDEX uq_incidents_active_dedup ON incidents (cctv_id, hazard_type, dedup_key) WHERE status IN ('DETECTED','CONFIRMED','SENT');
\ir ../../tests/database_contract.sql
COMMIT;
