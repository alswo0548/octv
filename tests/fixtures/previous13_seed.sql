INSERT INTO region VALUES ('11','Test','Test',NULL);
INSERT INTO agencies(id,name,agency_type,latitude,longitude,phone,region_code) VALUES(1,'Test','FIRE',37,127,'test','11');
INSERT INTO users(id,email,password_hash,name,role,agency_id) VALUES(1,'test@example.invalid','test','Test','RESPONDER',1);
INSERT INTO cctvs(id,external_cctv_id,name,provider,latitude,longitude) VALUES(1,'test','Test','test',37,127);INSERT INTO incidents(id,incident_no,cctv_id,hazard_type,confidence,model_version,detection_image_path,detection_bbox_json,dedup_key,status) VALUES(1,'T1',1,'test',0.98,'v1','test.jpg','[]','test','SENT');
INSERT INTO incident_contexts(id,incident_id,captured_at) VALUES(1,1,'2026-09-28');
INSERT INTO incident_agency_recommendations(id,recommendation_rank,recommendation_score,score_breakdown_json,rule_version,incident_id,agency_id) VALUES(1,1,80,'{}','r1',1,1);INSERT INTO route_candidates(id,route_name,distance_m,duration_sec,score_breakdown_json,route_path_json,rule_version,created_at,agency_recommendation_id) VALUES(1,'A',123,60,'{}','[]','r2','2026-09-28',1);
INSERT INTO notifications(id,incidents_id,agency_recommendation_id,agency_id,user_id) VALUES(1,1,1,1,1);