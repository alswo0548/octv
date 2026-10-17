"""monitoring_settings 초기 기본값 적재 스크립트."""

from backend.app.db.session import (
    get_connection,
)

from backend.app.settings.repository import (
    get_monitoring_settings,
)


# =========================================================
# 기본 설정값
# =========================================================

DEFAULT_SETTINGS = {
    "base_analysis_interval_sec": 5,
    "alert_analysis_interval_sec": 3,
    "verify_analysis_interval_sec": 2,

    "candidate_confidence_threshold": 0.70,
    "candidate_min_detection_count": 3,
    "temporal_validation_sec": 5,
    "incident_confidence_threshold": 0.85,

    "reconnect_interval_sec": 10,
    "max_reconnect_attempts": 3,

    "quality_threshold": 0.60,
}


# =========================================================
# 설정값 출력
# =========================================================

def print_settings(
    settings: dict,
) -> None:

    print(
        f"id                           : "
        f"{settings['id']}"
    )

    print(
        f"base_analysis_interval_sec   : "
        f"{settings['base_analysis_interval_sec']}"
    )

    print(
        f"alert_analysis_interval_sec  : "
        f"{settings['alert_analysis_interval_sec']}"
    )

    print(
        f"verify_analysis_interval_sec : "
        f"{settings['verify_analysis_interval_sec']}"
    )

    print(
        f"candidate_confidence         : "
        f"{settings['candidate_confidence_threshold']}"
    )

    print(
        f"candidate_min_count          : "
        f"{settings['candidate_min_detection_count']}"
    )

    print(
        f"temporal_validation_sec      : "
        f"{settings['temporal_validation_sec']}"
    )

    print(
        f"incident_confidence          : "
        f"{settings['incident_confidence_threshold']}"
    )

    print(
        f"reconnect_interval_sec       : "
        f"{settings['reconnect_interval_sec']}"
    )

    print(
        f"max_reconnect_attempts       : "
        f"{settings['max_reconnect_attempts']}"
    )

    print(
        f"quality_threshold            : "
        f"{settings['quality_threshold']}"
    )

    print(
        f"updated_by                   : "
        f"{settings['updated_by']}"
    )

    print(
        f"updated_at                   : "
        f"{settings['updated_at']}"
    )


# =========================================================
# Main
# =========================================================

def main() -> None:

    print("=" * 70)
    print("OCTV MONITORING SETTINGS SYNC")
    print("=" * 70)

    with get_connection() as connection:

        # =================================================
        # 1. 기존 설정 조회
        # =================================================

        existing = (
            get_monitoring_settings(
                connection
            )
        )

        # =================================================
        # 2. 이미 설정이 존재하면 덮어쓰지 않음
        # =================================================

        if existing is not None:

            print()
            print(
                "[SKIP] monitoring_settings에 "
                "이미 설정값이 존재합니다."
            )

            print()
            print_settings(
                existing
            )

            print()
            print(
                "[INFO] 기존 설정은 "
                "변경하지 않았습니다."
            )

            return

        # =================================================
        # 3. 초기 설정 INSERT
        # =================================================

        query = """
            INSERT INTO monitoring_settings (
                base_analysis_interval_sec,
                alert_analysis_interval_sec,
                verify_analysis_interval_sec,
                candidate_confidence_threshold,
                candidate_min_detection_count,
                temporal_validation_sec,
                incident_confidence_threshold,
                reconnect_interval_sec,
                max_reconnect_attempts,
                quality_threshold,
                updated_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NULL
            )
            RETURNING
                id,
                base_analysis_interval_sec,
                alert_analysis_interval_sec,
                verify_analysis_interval_sec,
                candidate_confidence_threshold,
                candidate_min_detection_count,
                temporal_validation_sec,
                incident_confidence_threshold,
                reconnect_interval_sec,
                max_reconnect_attempts,
                quality_threshold,
                updated_by,
                updated_at;
        """

        values = (
            DEFAULT_SETTINGS[
                "base_analysis_interval_sec"
            ],
            DEFAULT_SETTINGS[
                "alert_analysis_interval_sec"
            ],
            DEFAULT_SETTINGS[
                "verify_analysis_interval_sec"
            ],
            DEFAULT_SETTINGS[
                "candidate_confidence_threshold"
            ],
            DEFAULT_SETTINGS[
                "candidate_min_detection_count"
            ],
            DEFAULT_SETTINGS[
                "temporal_validation_sec"
            ],
            DEFAULT_SETTINGS[
                "incident_confidence_threshold"
            ],
            DEFAULT_SETTINGS[
                "reconnect_interval_sec"
            ],
            DEFAULT_SETTINGS[
                "max_reconnect_attempts"
            ],
            DEFAULT_SETTINGS[
                "quality_threshold"
            ],
        )

        with connection.cursor() as cursor:

            cursor.execute(
                query,
                values,
            )

            inserted = (
                cursor.fetchone()
            )

    # =====================================================
    # 4. 결과 출력
    # =====================================================

    print()
    print(
        "[INSERT] monitoring_settings "
        "기본 설정 생성"
    )

    print()
    print_settings(
        inserted
    )

    print()
    print(
        "[SUCCESS] "
        "monitoring_settings "
        "초기 설정 준비 완료"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()