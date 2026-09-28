-- 빈 DB 최초 생성용. psql -f database/schema.sql로 실행합니다.
-- 실제 테이블 정의는 schema/ 안에서 수정하세요. 기존 DB에는 재실행하지 않습니다.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO public;
\ir schema/00_enums.sql
\ir schema/10_regions.sql
\ir schema/20_agencies.sql
\ir schema/30_users.sql
\ir schema/40_cctvs.sql
\ir schema/50_monitoring_settings.sql
\ir schema/60_incidents.sql
\ir schema/70_weather_alerts.sql
\ir schema/80_incident_contexts.sql
\ir schema/90_incident_assessments.sql
\ir schema/100_agency_recommendations.sql
\ir schema/110_route_evaluations.sql
\ir schema/120_route_candidates.sql
\ir schema/130_notifications.sql
\ir schema/140_support_requests.sql
COMMIT;
