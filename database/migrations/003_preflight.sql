-- Read-only duplicate checks. No values/credentials are printed.
DO $preflight$
DECLARE conflict_ids BIGINT[];
BEGIN
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM users
        WHERE (lower(btrim(email))) IN (SELECT lower(btrim(email)) FROM users WHERE TRUE GROUP BY lower(btrim(email)) HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_users_email_normalized: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM cctvs
        WHERE (provider, external_cctv_id) IN (SELECT provider, external_cctv_id FROM cctvs WHERE TRUE GROUP BY provider, external_cctv_id HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_cctvs_provider_external: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM incidents
        WHERE (incident_no) IN (SELECT incident_no FROM incidents WHERE TRUE GROUP BY incident_no HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_incidents_incident_no: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM weather_alerts
        WHERE (external_alert_id, region_code) IN (SELECT external_alert_id, region_code FROM weather_alerts WHERE TRUE GROUP BY external_alert_id, region_code HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_weather_alerts_external_region: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM incident_agency_recommendations
        WHERE (incident_id, agency_id) IN (SELECT incident_id, agency_id FROM incident_agency_recommendations WHERE TRUE GROUP BY incident_id, agency_id HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_recommendations_incident_agency: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM notifications
        WHERE (agency_recommendation_id, user_id) IN (SELECT agency_recommendation_id, user_id FROM notifications WHERE TRUE GROUP BY agency_recommendation_id, user_id HAVING count(*)>1)
          AND TRUE;
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_notifications_recommendation_user: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
    SELECT array_agg(id ORDER BY id) INTO conflict_ids FROM incidents
        WHERE (cctv_id, hazard_type, dedup_key) IN (SELECT cctv_id, hazard_type, dedup_key FROM incidents WHERE status IN ('DETECTED','CONFIRMED','SENT') GROUP BY cctv_id, hazard_type, dedup_key HAVING count(*)>1)
          AND status IN ('DETECTED','CONFIRMED','SENT');
    IF conflict_ids IS NOT NULL THEN
        RAISE EXCEPTION 'Duplicate rows for uq_incidents_active_dedup: IDs %. Resolve data explicitly; no rows were changed.', conflict_ids;
    END IF;
END $preflight$;
