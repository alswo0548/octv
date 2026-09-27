# ERD 컬럼 대응표
첨부 ERD의 14개 테이블을 전사했다. PK의 ID 표시는 AUTO_INCREMENT를 의미한다.

| 테이블 | 컬럼 | PostgreSQL 타입 | NULL | 기본값 / PK | FK 대상 |
|---|---|---|---|---|---|
| region | region_code | VARCHAR(100) | 불가 | PK | - |
| region | sido_name | VARCHAR(100) | 불가 | - | - |
| region | sigungu_name | VARCHAR(100) | 불가 | - | - |
| region | weather_region_code | VARCHAR(500) | 허용 | - | - |
| agencies | id | BIGINT | 불가 | ID | - |
| agencies | name | VARCHAR(150) | 불가 | - | - |
| agencies | agency_type | agency_type_enum | 불가 | - | - |
| agencies | address | VARCHAR(255) | 허용 | - | - |
| agencies | latitude | DECIMAL(10,7) | 불가 | - | - |
| agencies | longitude | DECIMAL(10,7) | 불가 | - | - |
| agencies | phone | VARCHAR(30) | 불가 | - | - |
| agencies | region_code | VARCHAR(100) | 불가 | - | region.region_code |
| users | id | BIGINT | 불가 | ID | - |
| users | email | VARCHAR(255) | 불가 | - | - |
| users | password_hash | VARCHAR(255) | 불가 | - | - |
| users | name | VARCHAR(100) | 불가 | - | - |
| users | role | user_role_enum | 불가 | - | - |
| users | is_active | BOOLEAN | 불가 | TRUE | - |
| users | agency_id | BIGINT | 허용 | - | agencies.id |
| users | notification_enabled | BOOLEAN | 불가 | TRUE | - |
| cctvs | id | BIGINT | 불가 | ID | - |
| cctvs | external_cctv_id | VARCHAR(100) | 불가 | - | - |
| cctvs | name | VARCHAR(150) | 불가 | - | - |
| cctvs | provider | VARCHAR(100) | 불가 | - | - |
| cctvs | address | VARCHAR(255) | 허용 | - | - |
| cctvs | latitude | DECIMAL(10,7) | 불가 | - | - |
| cctvs | longitude | DECIMAL(10,7) | 불가 | - | - |
| cctvs | stream_url | VARCHAR(500) | 허용 | - | - |
| cctvs | is_monitored | BOOLEAN | 불가 | FALSE | - |
| cctvs | connection_status | connection_status_enum | 불가 | 'DISCONNECTED' | - |
| cctvs | video_quality_status | video_quality_enum | 허용 | - | - |
| cctvs | analysis_status | analysis_status_enum | 허용 | - | - |
| cctvs | last_frame_at | TIMESTAMP WITHOUT TIME ZONE | 허용 | - | - |
| cctvs | region_code | VARCHAR(100) | 허용 | - | region.region_code |
| cctvs | monitored_mode | monitored_mode_enum | 허용 | - | - |
| monitoring_settings | id | BIGINT | 불가 | ID | - |
| monitoring_settings | base_analysis_interval_sec | INT | 불가 | - | - |
| monitoring_settings | alert_analysis_interval_sec | INT | 불가 | - | - |
| monitoring_settings | verify_analysis_interval_sec | INT | 불가 | - | - |
| monitoring_settings | candidate_confidence_threshold | DECIMAL(5,4) | 불가 | - | - |
| monitoring_settings | candidate_min_detection_count | INT | 불가 | - | - |
| monitoring_settings | temporal_validation_sec | INT | 불가 | - | - |
| monitoring_settings | incident_confidence_threshold | DECIMAL(5,4) | 불가 | - | - |
| monitoring_settings | reconnect_interval_sec | INT | 불가 | - | - |
| monitoring_settings | max_reconnect_attempts | INT | 불가 | - | - |
| monitoring_settings | quality_threshold | DECIMAL(5,4) | 불가 | - | - |
| monitoring_settings | updated_by | BIGINT | 허용 | - | users.id |
| monitoring_settings | updated_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| incidents | id | BIGINT | 불가 | ID | - |
| incidents | incident_no | VARCHAR(50) | 불가 | - | - |
| incidents | cctv_id | BIGINT | 불가 | - | cctvs.id |
| incidents | hazard_type | VARCHAR(50) | 불가 | - | - |
| incidents | confidence | DECIMAL(5,4) | 불가 | - | - |
| incidents | model_version | VARCHAR(100) | 불가 | - | - |
| incidents | detection_image_path | VARCHAR(500) | 불가 | - | - |
| incidents | detection_bbox_json | JSON | 불가 | - | - |
| incidents | detection_duration_sec | INT | 불가 | - | - |
| incidents | dedup_key | VARCHAR(255) | 불가 | - | - |
| incidents | status | incident_status_enum | 불가 | 'DETECTED' | - |
| incidents | detected_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| incidents | last_detected_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| weather_alerts | id | BIGINT | 불가 | ID | - |
| weather_alerts | external_alert_id | VARCHAR(100) | 불가 | - | - |
| weather_alerts | alert_type | VARCHAR(50) | 불가 | - | - |
| weather_alerts | alert_level | VARCHAR(50) | 불가 | - | - |
| weather_alerts | title | VARCHAR(255) | 불가 | - | - |
| weather_alerts | issued_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | - | - |
| weather_alerts | ended_at | TIMESTAMP WITHOUT TIME ZONE | 허용 | - | - |
| weather_alerts | status | weather_status_enum | 불가 | 'ACTIVE' | - |
| weather_alerts | raw_data_json | JSON | 불가 | - | - |
| weather_alerts | region_code | VARCHAR(100) | 불가 | - | region.region_code |
| incident_contexts | id | BIGINT | 불가 | ID | - |
| incident_contexts | incident_id | BIGINT | 불가 | - | incidents.id |
| incident_contexts | weather_alert_id | BIGINT | 허용 | - | weather_alerts.id |
| incident_contexts | rainfall_mm | DECIMAL(7,2) | 허용 | - | - |
| incident_contexts | water_level_m | DECIMAL(7,2) | 허용 | - | - |
| incident_contexts | traffic_level | VARCHAR(30) | 허용 | - | - |
| incident_contexts | blocked_lane_count | INT | 허용 | - | - |
| incident_contexts | road_type | VARCHAR(50) | 허용 | - | - |
| incident_contexts | nearby_facility_type | VARCHAR(100) | 허용 | - | - |
| incident_contexts | nearby_facility_distance_m | INT | 허용 | - | - |
| incident_contexts | past_disaster_count | INT | 허용 | - | - |
| incident_contexts | raw_context_json | JSON | 불가 | - | - |
| incident_contexts | captured_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| incident_assessments | id | BIGINT | 불가 | ID | - |
| incident_assessments | incident_id | BIGINT | 불가 | - | incidents.id |
| incident_assessments | risk_score | DECIMAL(6,2) | 불가 | - | - |
| incident_assessments | risk_level | VARCHAR(30) | 불가 | - | - |
| incident_assessments | risk_breakdown_json | JSON | 불가 | - | - |
| incident_assessments | priority_score | DECIMAL(6,2) | 불가 | - | - |
| incident_assessments | priority | VARCHAR(30) | 불가 | - | - |
| incident_assessments | priority_breakdown_json | JSON | 불가 | - | - |
| incident_assessments | rule_version | VARCHAR(50) | 불가 | - | - |
| incident_agency_recommendations | id | BIGINT | 불가 | ID | - |
| incident_agency_recommendations | recommendation_rank | INT | 불가 | - | - |
| incident_agency_recommendations | recommendation_score | DECIMAL(6,2) | 불가 | - | - |
| incident_agency_recommendations | score_breakdown_json | JSON | 불가 | - | - |
| incident_agency_recommendations | rule_version | VARCHAR(50) | 불가 | - | - |
| incident_agency_recommendations | recommendation_status | recommendation_status_enum | 불가 | 'RECOMMENDED' | - |
| incident_agency_recommendations | recommended_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| incident_agency_recommendations | incident_id | BIGINT | 불가 | - | incidents.id |
| incident_agency_recommendations | agency_id | BIGINT | 불가 | - | agencies.id |
| route_evaluations | id | BIGINT | 불가 | ID | - |
| route_evaluations | rule_version | VARCHAR(50) | 불가 | - | - |
| route_evaluations | created_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| route_evaluations | agency_recommendation_id | BIGINT | 불가 | - | incident_agency_recommendations.id |
| route_candidates | id | BIGINT | 불가 | ID | - |
| route_candidates | route_name | VARCHAR(100) | 불가 | - | - |
| route_candidates | distance_m | INT | 불가 | - | - |
| route_candidates | duration_sec | INT | 불가 | - | - |
| route_candidates | traffic_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | control_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | hazard_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | accessibility_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | distance_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | total_score | DECIMAL(6,2) | 허용 | - | - |
| route_candidates | score_breakdown_json | JSON | 불가 | - | - |
| route_candidates | disqualify_reason | VARCHAR(500) | 허용 | - | - |
| route_candidates | route_path_json | JSON | 불가 | - | - |
| route_candidates | route_evaluation_id | BIGINT | 불가 | - | route_evaluations.id |
| notifications | id | BIGINT | 불가 | ID | - |
| notifications | read_at | TIMESTAMP WITHOUT TIME ZONE | 허용 | - | - |
| notifications | created_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| notifications | incidents_id | BIGINT | 불가 | - | incidents.id |
| notifications | route_evaluation_id | BIGINT | 불가 | - | route_evaluations.id |
| notifications | agency_id | BIGINT | 불가 | - | agencies.id |
| notifications | user_id | BIGINT | 불가 | - | users.id |
| incident_support_requests | id | BIGINT | 불가 | ID | - |
| incident_support_requests | incident_id | BIGINT | 불가 | - | incidents.id |
| incident_support_requests | responder_id | BIGINT | 불가 | - | users.id |
| incident_support_requests | support_type | support_type_enum | 불가 | - | - |
| incident_support_requests | request_content | TEXT | 불가 | - | - |
| incident_support_requests | created_at | TIMESTAMP WITHOUT TIME ZONE | 불가 | CURRENT_TIMESTAMP | - |
| incident_support_requests | agency_id | BIGINT | 불가 | - | agencies.id |
