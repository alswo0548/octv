-- Modify "incidents" table
ALTER TABLE "incidents" DROP COLUMN "detection_image_path", ADD COLUMN "representative_image" bytea NULL, ADD COLUMN "representative_image_updated_at" timestamp NULL;
-- Set comment to column: "representative_image" on table: "incidents"
COMMENT ON COLUMN "incidents"."representative_image" IS '사건 최신 대표 이미지 JPEG 바이너리';
-- Set comment to column: "representative_image_updated_at" on table: "incidents"
COMMENT ON COLUMN "incidents"."representative_image_updated_at" IS '대표 이미지 마지막 갱신 일시';
