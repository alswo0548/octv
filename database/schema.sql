-- 빈 DB 전용 초기화 진입점. 기존 DB에는 재실행하지 않습니다.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO public;
\ir ../backend/app/agencies/sql/enums.sql
\ir ../backend/app/auth/sql/enums.sql
\ir ../backend/app/cctvs/sql/enums.sql
\ir ../backend/app/incidents/sql/enums.sql
\ir ../backend/app/support_requests/sql/enums.sql
\ir ../backend/app/db/sql/region.sql
\ir ../backend/app/agencies/sql/agencies.sql
\ir ../backend/app/auth/sql/users.sql
\ir ../backend/app/cctvs/sql/cctvs.sql
\ir ../backend/app/settings/sql/monitoring_settings.sql
\ir ../backend/app/incidents/sql/incidents.sql
\ir ../backend/app/cctvs/sql/weather_alerts.sql
\ir ../backend/app/incidents/sql/incident_contexts.sql
\ir ../backend/app/incidents/sql/incident_assessments.sql
\ir ../backend/app/agencies/sql/incident_agency_recommendations.sql
\ir ../backend/app/routes/sql/route_candidates.sql
\ir ../backend/app/notifications/sql/notifications.sql
\ir ../backend/app/support_requests/sql/incident_support_requests.sql
COMMIT;
