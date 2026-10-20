"""선택한 개발 DB에서 통계·설정 SQL을 검사하고 테스트 데이터는 항상 rollback합니다.
실행 조건: OCTV_TEST_DATABASE_URL. 기존 스키마만 사용하며 초기화·삭제·마이그레이션은 하지 않습니다.
"""
import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from backend.app.stats import repository as stats
from backend.app.settings import repository as settings

@unittest.skipUnless(os.getenv("OCTV_TEST_DATABASE_URL"), "개발 DB URL 미지정: 실제 PostgreSQL 연결 대기")
class OperationsDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.connection = psycopg.connect(os.environ["OCTV_TEST_DATABASE_URL"], row_factory=dict_row)
        self.addCleanup(self.connection.close)
        self.addCleanup(self.connection.rollback)
        self.prefix = "OCTV-OPS-" + uuid4().hex
        self.region = self.prefix + "-R1"; self.other_region = self.prefix + "-R2"
        for region in (self.region, self.other_region):
            self.sql("INSERT INTO region(region_code,sido_name,sigungu_name) VALUES(%s,'TEST','TEST')", (region,))
        self.cctv = self.camera(self.region); self.other_cctv = self.camera(self.other_region)
        self.rows = []
        for index, (when, status, hazard, confidence) in enumerate((
            ("2026-10-19 14:59:59", "CONFIRMED", "flood", "0.1"),
            ("2026-10-19 15:00:00", "CONFIRMED", "severe_road_damage", "0.5"),
            ("2026-10-20 14:59:59", "SENT", "flood", "1.0"),
            ("2026-10-20 15:00:00", "RESOLVED", "fallen_tree", "0.7"),
            ("2026-10-20 01:00:00", "DETECTED", "road_obstacle", "0.4"),
            ("2026-10-20 02:00:00", "FALSE_POSITIVE", "road_obstacle", "0.9"),
        )):
            self.rows.append(self.sql("INSERT INTO incidents(incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key,status,detected_at,last_detected_at) VALUES(%s,%s,%s,%s,'TEST','[]',%s,%s,%s,%s) RETURNING id", (self.prefix + str(index), self.cctv, hazard, Decimal(confidence), self.prefix + str(index), status, when, when)).fetchone()["id"])
        self.sql("INSERT INTO incidents(incident_no,cctv_id,hazard_type,confidence,model_version,detection_bbox_json,dedup_key,status,detected_at,last_detected_at) VALUES(%s,%s,'flood',0.8,'TEST','[]',%s,'CONFIRMED','2026-10-20 01:00:00','2026-10-20 01:00:00')", (self.prefix + 'other', self.other_cctv, self.prefix + 'other'))
        for risk, priority in (("LOW", "P3"), ("HIGH", "P1")):
            self.sql("INSERT INTO incident_assessments(incident_id,risk_score,risk_level,risk_breakdown_json,priority_score,priority,priority_breakdown_json,rule_version) VALUES(%s,80,%s,'{}',80,%s,'{}','TEST')", (self.rows[1], risk, priority))
        for index in range(2):
            agency = self.sql("INSERT INTO agencies(name,agency_type,latitude,longitude,region_code) VALUES('TEST','ROAD_MANAGEMENT',37,127,%s) RETURNING id", (self.region,)).fetchone()["id"]
            self.sql("INSERT INTO incident_agency_recommendations(recommendation_rank,recommendation_score,score_breakdown_json,rule_version,incident_id,agency_id) VALUES(%s,80,'{}','TEST',%s,%s)", (index+1,self.rows[1],agency))

    def sql(self, text, params=()): return self.connection.execute(text, params)
    def camera(self, region):
        return self.sql("INSERT INTO cctvs(external_cctv_id,name,provider,latitude,longitude,region_code) VALUES(%s,'TEST','TEST',37,127,%s) RETURNING id", (region,region)).fetchone()["id"]
    def query(self, **changes):
        filters = dict(start=date(2026,10,20), end=date(2026,10,20), start_utc=datetime(2026,10,19,15), end_utc=datetime(2026,10,20,15), region_code=self.region, cctv_id=None, confirmed_only=True)
        return stats.aggregate_incidents(self.connection, filters | changes)

    def test_kst_boundaries_and_no_agency_or_assessment_duplicates(self):
        result = self.query()
        self.assertEqual(result["total_incident_count"], 2)
        self.assertEqual(result["confirmed_incident_count"], 2)
        self.assertEqual(result["by_hazard"], {"severe_road_damage":1,"flood":1})
        self.assertEqual(result["by_priority"], {"P1":1,"UNASSESSED":1})
        self.assertEqual(result["by_risk"], {"HIGH":1,"UNASSESSED":1})
        self.assertEqual(result["by_status"], {"CONFIRMED":1,"SENT":1})
        self.assertEqual(sum(p["count"] for p in result["daily"]), 2)
        self.assertEqual(result["hourly"][0]["count"], 1)
        self.assertEqual(result["hourly"][23]["count"], 1)
        self.assertEqual(result["confidence_distribution"], {"50-70":1,"90-100":1})
        self.assertEqual(float(result["average_confidence"]), 0.75)

    def test_all_status_scope_and_independent_camera_filter(self):
        result = self.query(confirmed_only=False)
        self.assertEqual(result["total_incident_count"], 4)
        self.assertEqual(result["confirmed_incident_count"], 2)
        self.assertEqual(sum(result["by_status"].values()), 4)
        self.assertEqual(sum(result["confidence_distribution"].values()), 4)
        self.assertEqual(self.query(region_code=None, cctv_id=self.other_cctv)["total_incident_count"], 1)
        self.assertEqual(self.query(cctv_id=self.other_cctv)["total_incident_count"], 0)

    def test_empty_range_and_zero_days(self):
        result = self.query(start=date(2026,10,22), end=date(2026,10,24), start_utc=datetime(2026,10,21,15), end_utc=datetime(2026,10,24,15))
        self.assertEqual(result["total_incident_count"], 0)
        self.assertEqual([p["count"] for p in result["daily"]], [0,0,0])
        self.assertIsNone(result["average_confidence"])
        self.assertEqual(sum(p["count"] for p in result["hourly"]), 0)

    def test_region_parameter_does_not_change_sql_scope(self):
        self.assertEqual(self.query(region_code="' OR 1=1 --")["total_incident_count"], 0)

    def test_settings_save_requery_and_all_runtime_columns_change(self):
        uid = self.sql(
            """
            INSERT INTO users(
                email,
                password_hash,
                name,
                role
            )
            VALUES(
                %s,
                'TEST',
                'TEST',
                'CONTROL_ADMIN'
            )
            RETURNING id
            """,
            (
                self.prefix
                + "@example.invalid",
            ),
        ).fetchone()["id"]

        sid = self.sql(
            """
            INSERT INTO monitoring_settings(
                base_analysis_interval_sec,
                alert_analysis_interval_sec,
                verify_analysis_interval_sec,
                candidate_confidence_threshold,
                candidate_min_detection_count,
                temporal_validation_sec,
                incident_confidence_threshold,
                reconnect_interval_sec,
                max_reconnect_attempts,
                quality_threshold
            )
            VALUES(
                10,
                5,
                1,
                0.35,
                3,
                5,
                0.70,
                3,
                5,
                0.60
            )
            RETURNING id
            """
        ).fetchone()["id"]

        values = dict(
            base_analysis_interval_sec=12,
            alert_analysis_interval_sec=4,
            verify_analysis_interval_sec=2,

            candidate_confidence_threshold=Decimal(
                "0.40"
            ),
            candidate_min_detection_count=4,
            temporal_validation_sec=15,
            incident_confidence_threshold=Decimal(
                "0.45"
            ),

            reconnect_interval_sec=8,
            max_reconnect_attempts=7,

            quality_threshold=Decimal(
                "0.65"
            ),
        )

        settings.save_monitoring_settings(
            self.connection,
            sid,
            values,
            uid,
        )

        row = self.sql(
            """
            SELECT *
            FROM monitoring_settings
            WHERE id = %s
            """,
            (
                sid,
            ),
        ).fetchone()

        self.assertEqual(
            row[
                "base_analysis_interval_sec"
            ],
            12,
        )

        self.assertEqual(
            row[
                "alert_analysis_interval_sec"
            ],
            4,
        )

        self.assertEqual(
            row[
                "verify_analysis_interval_sec"
            ],
            2,
        )

        self.assertEqual(
            Decimal(
                str(
                    row[
                        "candidate_confidence_threshold"
                    ]
                )
            ),
            Decimal(
                "0.40"
            ),
        )

        self.assertEqual(
            row[
                "candidate_min_detection_count"
            ],
            4,
        )

        self.assertEqual(
            row[
                "temporal_validation_sec"
            ],
            15,
        )

        self.assertEqual(
            Decimal(
                str(
                    row[
                        "incident_confidence_threshold"
                    ]
                )
            ),
            Decimal(
                "0.45"
            ),
        )

        self.assertEqual(
            row[
                "reconnect_interval_sec"
            ],
            8,
        )

        self.assertEqual(
            row[
                "max_reconnect_attempts"
            ],
            7,
        )

        self.assertEqual(
            Decimal(
                str(
                    row[
                        "quality_threshold"
                    ]
                )
            ),
            Decimal(
                "0.65"
            ),
        )

        self.assertEqual(
            row[
                "updated_by"
            ],
            uid,
        )

        delta = self.sql(
            """
            SELECT
                ABS(
                    EXTRACT(
                        EPOCH FROM (
                            updated_at
                            - (
                                CURRENT_TIMESTAMP
                                AT TIME ZONE 'UTC'
                            )
                        )
                    )
                ) AS seconds
            FROM monitoring_settings
            WHERE id = %s
            """,
            (
                sid,
            ),
        ).fetchone()["seconds"]

        self.assertLess(
            float(
                delta
            ),
            1,
        )

if __name__ == '__main__': unittest.main()
