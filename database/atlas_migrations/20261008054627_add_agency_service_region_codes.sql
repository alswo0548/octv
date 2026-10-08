-- Modify "agencies" table
ALTER TABLE "agencies" ADD COLUMN "service_region_codes" text[] NULL;
-- Set comment to column: "service_region_codes" on table: "agencies"
COMMENT ON COLUMN "agencies"."service_region_codes" IS 'ROAD_MANAGEMENT 기관의 담당 지역코드 목록';
-- Modify "region" table
ALTER TABLE "region"
ALTER COLUMN "weather_region_code" TYPE text[]
USING CASE
    WHEN "weather_region_code" IS NULL THEN NULL
    ELSE ARRAY["weather_region_code"::text]
END;
-- Set comment to column: "weather_region_code" on table: "region"
COMMENT ON COLUMN "region"."weather_region_code" IS '기상특보 API 지역코드 목록';
-- Set comment to table: "users"
COMMENT ON TABLE "users" IS '관제 관리자·기관 담당자·현장 담당자';
