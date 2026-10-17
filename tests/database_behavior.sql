-- CI-only transactional behavior tests. No production records are committed.
BEGIN;
CREATE FUNCTION pg_temp.expect_unique(statement TEXT, expected_constraint TEXT) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE got TEXT;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN unique_violation THEN
        GET STACKED DIAGNOSTICS got = CONSTRAINT_NAME;
        IF got <> expected_constraint THEN RAISE EXCEPTION 'Wrong UNIQUE rule: %', got; END IF;
        RETURN;
    END;
    RAISE EXCEPTION 'Expected UNIQUE rejection: %', expected_constraint;
END $$;
INSERT INTO region VALUES ('test-r1','Test','One',NULL),('test-r2','Test','Two',NULL);
INSERT INTO agencies (id,name,agency_type,latitude,longitude,region_code) VALUES
    (-1,'Test agency','FIRE',37,127,'test-r1'),(-2,'Test agency','FIRE',37,127,'test-r2');
INSERT INTO users (id,email,password_hash,name,role,agency_id) VALUES
    (-1,'test@example.invalid','test-only','Test','RESPONDER',-1),
    (-2,'other@example.invalid','test-only','Test','RESPONDER',-1);
SELECT pg_temp.expect_unique($q$INSERT INTO users (email,password_hash,name,role) VALUES
    (' TEST@EXAMPLE.INVALID ','x','Test','RESPONDER')$q$,'uq_users_email_normalized');
INSERT INTO cctvs (id,external_cctv_id,name,provider,latitude,longitude) VALUES
    (-1,'camera-1','Test','provider-a',37,127),(-2,'camera-1','Test','provider-b',37,127);
SELECT pg_temp.expect_unique($q$INSERT INTO cctvs (external_cctv_id,name,provider,latitude,longitude)
    VALUES ('camera-1','Different name','provider-a',37,127)$q$,'uq_cctvs_provider_external');
INSERT INTO incidents (id,incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key,status)
    VALUES (-1,'TEST-1',-1,'test',0.9,'test','{}','same-location-window','DETECTED');
SELECT pg_temp.expect_unique($q$INSERT INTO incidents (incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key)
    VALUES ('TEST-1',-2,'test',0.9,'test','{}','other')$q$,'uq_incidents_incident_no');
SELECT pg_temp.expect_unique($q$INSERT INTO incidents (incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key,status)
    VALUES ('TEST-2',-1,'test',0.9,'test','{}','same-location-window','SENT')$q$,'uq_incidents_active_dedup');
-- Terminal cases free the dedup key; another CCTV and another hazard may also use it.
UPDATE incidents SET status='RESOLVED' WHERE id=-1;
INSERT INTO incidents (id,incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key,status)
    VALUES (-2,'TEST-2',-1,'test',0.9,'test','{}','same-location-window','CONFIRMED'),
           (-3,'TEST-3',-1,'test',0.9,'test','{}','same-location-window','FALSE_POSITIVE'),
           (-4,'TEST-4',-2,'test',0.9,'test','{}','same-location-window','DETECTED'),
           (-5,'TEST-5',-1,'another-hazard',0.9,'test','{}','same-location-window','DETECTED');
SELECT pg_temp.expect_unique($q$UPDATE incidents SET status='DETECTED' WHERE id=-1$q$,'uq_incidents_active_dedup');
INSERT INTO weather_alerts (id,external_alert_id,alert_type,alert_level,title,issued_at,region_code)
    VALUES (-1,'weather-1','rain','warning','Test',CURRENT_TIMESTAMP,'test-r1'),
           (-2,'weather-1','rain','warning','Test',CURRENT_TIMESTAMP,'test-r2');
SELECT pg_temp.expect_unique($q$INSERT INTO weather_alerts (external_alert_id,alert_type,alert_level,title,issued_at,region_code)
    VALUES ('weather-1','rain','warning','Test',CURRENT_TIMESTAMP,'test-r1')$q$,'uq_weather_alerts_external_region');
INSERT INTO incident_agency_recommendations (id,recommendation_rank,recommendation_score,score_breakdown_json,rule_version,recommendation_status,incident_id,agency_id)
    VALUES (-1,1,90,'{}','test','COMPLETED',-1,-1),(-2,1,90,'{}','test','RECOMMENDED',-1,-2);
SELECT pg_temp.expect_unique($q$INSERT INTO incident_agency_recommendations (recommendation_rank,recommendation_score,score_breakdown_json,rule_version,incident_id,agency_id)
    VALUES (2,80,'{}','test',-1,-1)$q$,'uq_recommendations_incident_agency');
INSERT INTO notifications (id,incidents_id,agency_id,user_id,agency_recommendation_id)
    VALUES (-1,-1,-1,-1,-1),(-2,-1,-1,-2,-1);
SELECT pg_temp.expect_unique($q$INSERT INTO notifications (incidents_id,agency_id,user_id,agency_recommendation_id)
    VALUES (-1,-1,-1,-1)$q$,'uq_notifications_recommendation_user');
-- Multiple snapshots / evaluation records / route candidates are intentionally allowed.
INSERT INTO incident_contexts (id,incident_id) VALUES (-1,-1),(-2,-1);
INSERT INTO incident_assessments (id,incident_id,risk_score,risk_level,risk_breakdown_json,priority_score,priority,priority_breakdown_json,rule_version)
    VALUES (-1,-1,10,'test','{}',10,'test','{}','test'),(-2,-1,10,'test','{}',10,'test','{}','test');
INSERT INTO route_candidates (id,route_name,distance_m,duration_sec,route_path_json,rule_version,agency_recommendation_id)
    VALUES (-1,'A',100,10,'[]','test',-1),(-2,'A',110,11,'[]','test',-1);
DO $$ BEGIN
    BEGIN INSERT INTO incident_contexts (incident_id,captured_at) VALUES (-1,NULL);
    EXCEPTION WHEN not_null_violation THEN RETURN; END;
    RAISE EXCEPTION 'captured_at must reject NULL';
END $$;
ROLLBACK;
