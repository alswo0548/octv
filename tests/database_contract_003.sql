-- 最新 ERD 대응 검사. 읽기 전용이며 업무 데이터를 변경하지 않습니다.
DO $verify$
DECLARE
    expected JSONB := $expected${"columns": [["agencies", "address", "character varying(255)", false, ""], ["agencies", "agency_type", "agency_type_enum", true, ""], ["agencies", "id", "bigint", true, "d"], ["agencies", "latitude", "numeric(10,7)", true, ""], ["agencies", "longitude", "numeric(10,7)", true, ""], ["agencies", "name", "character varying(150)", true, ""], ["agencies", "phone", "character varying(30)", false, ""], ["agencies", "region_code", "character varying(100)", true, ""], ["cctvs", "address", "character varying(255)", false, ""], ["cctvs", "analysis_status", "analysis_status_enum", false, ""], ["cctvs", "connection_status", "connection_status_enum", true, ""], ["cctvs", "external_cctv_id", "character varying(100)", true, ""], ["cctvs", "id", "bigint", true, "d"], ["cctvs", "is_monitored", "boolean", true, ""], ["cctvs", "last_frame_at", "timestamp without time zone", false, ""], ["cctvs", "latitude", "numeric(10,7)", true, ""], ["cctvs", "longitude", "numeric(10,7)", true, ""], ["cctvs", "monitored_mode", "monitored_mode_enum", false, ""], ["cctvs", "name", "character varying(150)", true, ""], ["cctvs", "provider", "character varying(100)", true, ""], ["cctvs", "region_code", "character varying(100)", false, ""], ["cctvs", "stream_url", "character varying(500)", false, ""], ["cctvs", "video_quality_status", "video_quality_enum", false, ""], ["incident_agency_recommendations", "agency_id", "bigint", true, ""], ["incident_agency_recommendations", "id", "bigint", true, "d"], ["incident_agency_recommendations", "incident_id", "bigint", true, ""], ["incident_agency_recommendations", "recommendation_rank", "integer", true, ""], ["incident_agency_recommendations", "recommendation_score", "numeric(6,2)", true, ""], ["incident_agency_recommendations", "recommendation_status", "recommendation_status_enum", true, ""], ["incident_agency_recommendations", "rule_version", "character varying(50)", true, ""], ["incident_agency_recommendations", "score_breakdown_json", "json", true, ""], ["incident_assessments", "id", "bigint", true, "d"], ["incident_assessments", "incident_id", "bigint", true, ""], ["incident_assessments", "priority", "character varying(30)", true, ""], ["incident_assessments", "priority_breakdown_json", "json", true, ""], ["incident_assessments", "priority_score", "numeric(6,2)", true, ""], ["incident_assessments", "risk_breakdown_json", "json", true, ""], ["incident_assessments", "risk_level", "character varying(30)", true, ""], ["incident_assessments", "risk_score", "numeric(6,2)", true, ""], ["incident_assessments", "rule_version", "character varying(50)", true, ""], ["incident_contexts", "blocked_lane_count", "integer", false, ""], ["incident_contexts", "captured_at", "timestamp without time zone", true, ""], ["incident_contexts", "id", "bigint", true, "d"], ["incident_contexts", "incident_id", "bigint", true, ""], ["incident_contexts", "nearby_facility_distance_m", "integer", false, ""], ["incident_contexts", "nearby_facility_type", "character varying(100)", false, ""], ["incident_contexts", "past_disaster_count", "integer", false, ""], ["incident_contexts", "rainfall_mm", "numeric(7,2)", false, ""], ["incident_contexts", "road_type", "character varying(50)", false, ""], ["incident_contexts", "traffic_level", "character varying(30)", false, ""], ["incident_contexts", "water_level_m", "numeric(7,2)", false, ""], ["incident_contexts", "weather_alert_id", "bigint", false, ""], ["incident_support_requests", "agency_id", "bigint", true, ""], ["incident_support_requests", "created_at", "timestamp without time zone", true, ""], ["incident_support_requests", "id", "bigint", true, "d"], ["incident_support_requests", "incident_id", "bigint", true, ""], ["incident_support_requests", "request_content", "text", true, ""], ["incident_support_requests", "responder_id", "bigint", true, ""], ["incident_support_requests", "support_type", "support_type_enum", true, ""], ["incidents", "cctv_id", "bigint", true, ""], ["incidents", "confidence", "numeric(5,4)", true, ""], ["incidents", "dedup_key", "character varying(255)", true, ""], ["incidents", "detected_at", "timestamp without time zone", true, ""], ["incidents", "detection_bbox_json", "json", true, ""], ["incidents", "detection_image_path", "character varying(500)", true, ""], ["incidents", "hazard_type", "character varying(50)", true, ""], ["incidents", "id", "bigint", true, "d"], ["incidents", "incident_no", "character varying(50)", true, ""], ["incidents", "last_detected_at", "timestamp without time zone", true, ""], ["incidents", "model_version", "character varying(100)", true, ""], ["incidents", "status", "incident_status_enum", true, ""], ["monitoring_settings", "alert_analysis_interval_sec", "integer", true, ""], ["monitoring_settings", "base_analysis_interval_sec", "integer", true, ""], ["monitoring_settings", "candidate_confidence_threshold", "numeric(5,4)", true, ""], ["monitoring_settings", "candidate_min_detection_count", "integer", true, ""], ["monitoring_settings", "id", "bigint", true, "d"], ["monitoring_settings", "incident_confidence_threshold", "numeric(5,4)", true, ""], ["monitoring_settings", "max_reconnect_attempts", "integer", true, ""], ["monitoring_settings", "quality_threshold", "numeric(5,4)", true, ""], ["monitoring_settings", "reconnect_interval_sec", "integer", true, ""], ["monitoring_settings", "temporal_validation_sec", "integer", true, ""], ["monitoring_settings", "updated_at", "timestamp without time zone", true, ""], ["monitoring_settings", "updated_by", "bigint", false, ""], ["monitoring_settings", "verify_analysis_interval_sec", "integer", true, ""], ["notifications", "agency_id", "bigint", true, ""], ["notifications", "agency_recommendation_id", "bigint", true, ""], ["notifications", "created_at", "timestamp without time zone", true, ""], ["notifications", "id", "bigint", true, "d"], ["notifications", "incidents_id", "bigint", true, ""], ["notifications", "read_at", "timestamp without time zone", false, ""], ["notifications", "user_id", "bigint", true, ""], ["region", "region_code", "character varying(100)", true, ""], ["region", "sido_name", "character varying(100)", true, ""], ["region", "sigungu_name", "character varying(100)", true, ""], ["region", "weather_region_code", "character varying(500)", false, ""], ["route_candidates", "agency_recommendation_id", "bigint", true, ""], ["route_candidates", "created_at", "timestamp without time zone", true, ""], ["route_candidates", "disqualify_reason", "character varying(500)", false, ""], ["route_candidates", "distance_m", "integer", true, ""], ["route_candidates", "duration_sec", "integer", true, ""], ["route_candidates", "id", "bigint", true, "d"], ["route_candidates", "route_name", "character varying(100)", true, ""], ["route_candidates", "route_path_json", "json", true, ""], ["route_candidates", "rule_version", "character varying(50)", true, ""], ["route_candidates", "score_breakdown_json", "json", false, ""], ["route_candidates", "total_score", "numeric(6,2)", false, ""], ["users", "agency_id", "bigint", false, ""], ["users", "email", "character varying(255)", true, ""], ["users", "id", "bigint", true, "d"], ["users", "is_active", "boolean", true, ""], ["users", "name", "character varying(100)", true, ""], ["users", "notification_enabled", "boolean", true, ""], ["users", "password_hash", "character varying(255)", true, ""], ["users", "role", "user_role_enum", true, ""], ["weather_alerts", "alert_level", "character varying(50)", true, ""], ["weather_alerts", "alert_type", "character varying(50)", true, ""], ["weather_alerts", "ended_at", "timestamp without time zone", false, ""], ["weather_alerts", "external_alert_id", "character varying(100)", true, ""], ["weather_alerts", "id", "bigint", true, "d"], ["weather_alerts", "issued_at", "timestamp without time zone", true, ""], ["weather_alerts", "region_code", "character varying(100)", true, ""], ["weather_alerts", "status", "weather_status_enum", true, ""], ["weather_alerts", "title", "character varying(255)", true, ""]], "pks": [["agencies", "id"], ["cctvs", "id"], ["incident_agency_recommendations", "id"], ["incident_assessments", "id"], ["incident_contexts", "id"], ["incident_support_requests", "id"], ["incidents", "id"], ["monitoring_settings", "id"], ["notifications", "id"], ["region", "region_code"], ["route_candidates", "id"], ["users", "id"], ["weather_alerts", "id"]], "fks": [["agencies", "region_code", "region", "region_code"], ["cctvs", "region_code", "region", "region_code"], ["incident_agency_recommendations", "agency_id", "agencies", "id"], ["incident_agency_recommendations", "incident_id", "incidents", "id"], ["incident_assessments", "incident_id", "incidents", "id"], ["incident_contexts", "incident_id", "incidents", "id"], ["incident_contexts", "weather_alert_id", "weather_alerts", "id"], ["incident_support_requests", "agency_id", "agencies", "id"], ["incident_support_requests", "incident_id", "incidents", "id"], ["incident_support_requests", "responder_id", "users", "id"], ["incidents", "cctv_id", "cctvs", "id"], ["monitoring_settings", "updated_by", "users", "id"], ["notifications", "agency_id", "agencies", "id"], ["notifications", "agency_recommendation_id", "incident_agency_recommendations", "id"], ["notifications", "incidents_id", "incidents", "id"], ["notifications", "user_id", "users", "id"], ["route_candidates", "agency_recommendation_id", "incident_agency_recommendations", "id"], ["users", "agency_id", "agencies", "id"], ["weather_alerts", "region_code", "region", "region_code"]], "enums": {"user_role_enum": ["CONTROL_ADMIN", "AGENCY_STAFF", "RESPONDER"], "incident_status_enum": ["DETECTED", "CONFIRMED", "SENT", "RESOLVED", "FALSE_POSITIVE"], "connection_status_enum": ["CONNECTED", "DISCONNECTED", "RECONNECTING"], "video_quality_enum": ["GOOD", "LOW", "UNAVAILABLE"], "analysis_status_enum": ["RUNNING", "STOPPED", "ERROR"], "monitored_mode_enum": ["BASE", "ALERT", "VERIFY", "POST_ALERT", "OFF"], "weather_status_enum": ["ACTIVE", "ENDED"], "agency_type_enum": ["FIRE", "POLICE", "ROAD_MANAGEMENT", "LOCAL_GOVERNMENT"], "recommendation_status_enum": ["RECOMMENDED", "DELIVERED", "COMPLETED"], "support_type_enum": ["PERSONNEL", "EQUIPMENT", "TRAFFIC_CONTROL", "OTHER"]}}$expected$::jsonb;
    actual JSONB;
    item RECORD;
BEGIN
    SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),
        a.attnotnull,a.attidentity::text) ORDER BY c.relname,a.attname) INTO actual
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_attribute a ON a.attrelid=c.oid
    WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped;
    IF actual IS DISTINCT FROM expected->'columns' THEN
        RAISE EXCEPTION 'ERD column/type/nullability/identity mismatch. Run the proper migration; do not reset the volume.';
    END IF;
    SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname) ORDER BY c.relname,a.attname) INTO actual
    FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=ANY(k.conkey)
    WHERE n.nspname='public' AND k.contype='p';
    IF actual IS DISTINCT FROM expected->'pks' THEN RAISE EXCEPTION 'ERD primary key mismatch'; END IF;
    SELECT jsonb_agg(jsonb_build_array(c.relname,a.attname,rc.relname,ra.attname)
        ORDER BY c.relname,a.attname,rc.relname,ra.attname) INTO actual
    FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_class rc ON rc.oid=k.confrelid
    JOIN LATERAL unnest(k.conkey,k.confkey) AS keys(col,refcol) ON true
    JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=keys.col
    JOIN pg_attribute ra ON ra.attrelid=rc.oid AND ra.attnum=keys.refcol
    WHERE n.nspname='public' AND k.contype='f';
    IF actual IS DISTINCT FROM expected->'fks' THEN RAISE EXCEPTION 'ERD foreign key mismatch'; END IF;
    IF (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typtype='e') <> 10 THEN
        RAISE EXCEPTION 'Expected exactly 10 ENUM types';
    END IF;
    FOR item IN SELECT key,value FROM jsonb_each(expected->'enums') LOOP
        SELECT jsonb_agg(e.enumlabel ORDER BY e.enumsortorder) INTO actual
        FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace JOIN pg_enum e ON e.enumtypid=t.oid
        WHERE n.nspname='public' AND t.typname=item.key;
        IF actual IS DISTINCT FROM item.value THEN RAISE EXCEPTION 'ERD ENUM mismatch: %',item.key; END IF;
    END LOOP;
    RAISE NOTICE 'SCHEMA OK: 13 tables, 123 columns, 19 foreign keys, 10 ENUMs';
END $verify$;

DO $unique_verify$
DECLARE actual JSONB; wanted JSONB := '[
 ["cctvs","uq_cctvs_provider_external","UNIQUE (provider, external_cctv_id)"],
 ["incident_agency_recommendations","uq_recommendations_incident_agency","UNIQUE (incident_id, agency_id)"],
 ["incidents","uq_incidents_incident_no","UNIQUE (incident_no)"],
 ["notifications","uq_notifications_recommendation_user","UNIQUE (agency_recommendation_id, user_id)"],
 ["weather_alerts","uq_weather_alerts_external_region","UNIQUE (external_alert_id, region_code)"]]'::jsonb;
BEGIN
    SELECT jsonb_agg(jsonb_build_array(t.relname,k.conname,pg_get_constraintdef(k.oid)) ORDER BY t.relname,k.conname)
        INTO actual FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public' AND k.contype='u';
    IF actual IS DISTINCT FROM wanted THEN RAISE EXCEPTION 'UNIQUE constraint mismatch'; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='users'
        AND indexname='uq_users_email_normalized'
        AND indexdef='CREATE UNIQUE INDEX uq_users_email_normalized ON public.users USING btree (lower(btrim((email)::text)))') THEN
        RAISE EXCEPTION 'Normalized email UNIQUE index mismatch';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND tablename='incidents'
        AND indexname='uq_incidents_active_dedup'
        AND indexdef=$idx$CREATE UNIQUE INDEX uq_incidents_active_dedup ON public.incidents USING btree (cctv_id, hazard_type, dedup_key) WHERE (status = ANY (ARRAY['DETECTED'::incident_status_enum, 'CONFIRMED'::incident_status_enum, 'SENT'::incident_status_enum]))$idx$) THEN
        RAISE EXCEPTION 'Active incident UNIQUE index mismatch';
    END IF;
    IF (SELECT count(*) FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname='public' AND i.indisunique AND NOT i.indisprimary)<>7 THEN
        RAISE EXCEPTION 'Expected exactly 7 additional UNIQUE rules';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='public'
        AND (NOT i.indisvalid OR NOT i.indisready)) THEN
        RAISE EXCEPTION 'Invalid or unready index';
    END IF;
    RAISE NOTICE 'UNIQUE OK: 5 constraints and 2 expression/partial indexes';
END $unique_verify$;
