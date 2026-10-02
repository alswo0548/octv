CREATE TABLE region (
    region_code VARCHAR(100) PRIMARY KEY,
    sido_name VARCHAR(100) NOT NULL,
    sigungu_name VARCHAR(100) NOT NULL,
    weather_region_code VARCHAR(500)
);
COMMENT ON TABLE region IS '지역코드';
COMMENT ON COLUMN region.region_code IS '지역코드 ID';
COMMENT ON COLUMN region.sido_name IS '시도 이름';
COMMENT ON COLUMN region.sigungu_name IS '시군구 이름';
COMMENT ON COLUMN region.weather_region_code IS '기상특보 API 지역코드';
