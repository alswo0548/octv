"""CI PostgreSQL integration checks.

Creates and drops only new octv_migration_* test DBs.
"""

import os
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]


def psql(
    dbname,
    path=None,
    statement=None,
    backup=True,
    success=True,
):
    args = [
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
    ]

    if backup is not None:
        args += [
            "-v",
            (
                "backup_confirmed="
                + (
                    "1"
                    if backup
                    else "0"
                )
            ),
        ]

    if path:
        args += [
            "-f",
            str(
                ROOT
                / path
            ),
        ]

    result = subprocess.run(
        args,
        input=statement,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env={
            **os.environ,
            "PGDATABASE":
                dbname,
        },
        cwd=ROOT,
    )

    if (
        success
        and result.returncode
    ):
        raise AssertionError(
            result.stderr
        )

    if (
        not success
        and not result.returncode
    ):
        raise AssertionError(
            "Expected migration "
            "to be refused"
        )

    return result


def main():
    """
    기존 legacy / previous DB 형태가
    현재 최종 스키마까지 정상적으로
    migration되는지 확인한다.

    기존 DB를 reset하지 않고
    매 테스트마다 새로운 임시 DB를 생성한다.
    """

    cases = [
        (
            "legacy14",
            None,
        ),
        (
            "previous13",
            None,
        ),
        (
            "legacy14",
            "duplicate",
        ),
        (
            "previous13",
            "null",
        ),
        (
            "previous13",
            "mismatch",
        ),
        (
            "previous13",
            "backup_guard",
        ),
        (
            "previous13",
            "backup_false",
        ),
    ]

    with psycopg.connect(
        "",
        autocommit=True,
    ) as admin:

        for (
            shape,
            issue,
        ) in cases:

            name = (
                "octv_migration_"
                + uuid4().hex
            )

            admin.execute(
                sql.SQL(
                    "CREATE DATABASE {}"
                ).format(
                    sql.Identifier(
                        name
                    )
                )
            )

            try:
                # ---------------------------------------------
                # Legacy / previous DB fixture 생성
                # ---------------------------------------------

                psql(
                    name,
                    (
                        f"tests/fixtures/"
                        f"{shape}.sql"
                    ),
                )

                psql(
                    name,
                    (
                        f"tests/fixtures/"
                        f"{shape}_seed.sql"
                    ),
                )

                # ---------------------------------------------
                # 실패 케이스용 데이터 조작
                # ---------------------------------------------

                if issue == "duplicate":

                    psql(
                        name,
                        statement=(
                            "INSERT INTO users("
                            "id,email,password_hash,"
                            "name,role"
                            ") VALUES("
                            "2,"
                            "' TEST@EXAMPLE.INVALID ',"
                            "'x',"
                            "'Test',"
                            "'RESPONDER'"
                            ");"
                        ),
                    )

                elif issue == "null":

                    psql(
                        name,
                        statement=(
                            "UPDATE incident_contexts "
                            "SET captured_at=NULL;"
                        ),
                    )

                elif issue == "mismatch":

                    psql(
                        name,
                        statement=(
                            "INSERT INTO agencies("
                            "id,name,agency_type,"
                            "latitude,longitude,"
                            "phone,region_code"
                            ") VALUES("
                            "2,"
                            "'Other',"
                            "'POLICE',"
                            "37,"
                            "127,"
                            "'test',"
                            "'11'"
                            "); "
                            "UPDATE notifications "
                            "SET agency_id=2;"
                        ),
                    )

                # ---------------------------------------------
                # 기존 수동 Migration
                # ---------------------------------------------

                result = psql(
                    name,
                    (
                        "database/migrations/"
                        "003_final_erd_uniques.sql"
                    ),
                    backup=(
                        None
                        if issue
                        == "backup_guard"
                        else issue
                        != "backup_false"
                    ),
                    success=(
                        issue
                        is None
                    ),
                )

                with psycopg.connect(
                    dbname=name,
                    autocommit=True,
                ) as check:

                    # -----------------------------------------
                    # 실패 케이스
                    # -----------------------------------------

                    if issue:

                        expected = {
                            "duplicate":
                                (
                                    "uq_users_email_"
                                    "normalized"
                                ),

                            "null":
                                (
                                    "captured_at "
                                    "contains NULL"
                                ),

                            "mismatch":
                                (
                                    "Notification "
                                    "incident/agency "
                                    "mismatch"
                                ),

                            "backup_guard":
                                (
                                    "create a backup "
                                    "first"
                                ),

                            "backup_false":
                                (
                                    "create a backup "
                                    "first"
                                ),
                        }[
                            issue
                        ]

                        assert (
                            expected
                            in (
                                result.stderr
                                + result.stdout
                            )
                        ), result.stderr

                        if (
                            shape
                            == "legacy14"
                        ):
                            assert (
                                check.execute(
                                    (
                                        "SELECT "
                                        "to_regclass("
                                        "'route_evaluations'"
                                        ") IS NOT NULL"
                                    )
                                )
                                .fetchone()[0]
                            )

                            assert (
                                check.execute(
                                    (
                                        "SELECT "
                                        "detection_duration_sec "
                                        "FROM incidents"
                                    )
                                )
                                .fetchone()[0]
                                == 5
                            )

                        else:
                            psql(
                                name,
                                (
                                    "database/migrations/"
                                    "002_contract.sql"
                                ),
                            )

                    # -----------------------------------------
                    # 정상 Migration 케이스
                    # -----------------------------------------

                    else:

                        # 2026-10-08
                        # 기관 담당 지역 / 기상 지역코드 배열화
                        psql(
                            name,
                            (
                                "database/"
                                "atlas_migrations/"
                                "20261008054627_"
                                "add_agency_service_"
                                "region_codes.sql"
                            ),
                        )

                        # 2026-10-14
                        # incidents.detection_image_path 제거
                        # 대표 이미지 BYTEA 컬럼 추가
                        psql(
                            name,
                            (
                                "database/"
                                "atlas_migrations/"
                                "20261014014249_"
                                "incident_"
                                "representative_image.sql"
                            ),
                        )

                        # 최신 ERD 계약 검증
                        psql(
                            name,
                            (
                                "tests/"
                                "database_contract.sql"
                            ),
                        )

                        # -------------------------------------
                        # 기존 데이터 보존 확인
                        # -------------------------------------

                        assert (
                            check.execute(
                                (
                                    "SELECT "
                                    "rule_version, "
                                    "distance_m, "
                                    "agency_recommendation_id, "
                                    "created_at::text "
                                    "FROM route_candidates"
                                )
                            )
                            .fetchone()
                            == (
                                "r2",
                                123,
                                1,
                                (
                                    "2026-09-28 "
                                    "00:00:00"
                                ),
                            )
                        )

                        assert (
                            check.execute(
                                (
                                    "SELECT "
                                    "agency_recommendation_id "
                                    "FROM notifications"
                                )
                            )
                            .fetchone()[0]
                            == 1
                        )

                        if (
                            shape
                            == "legacy14"
                        ):
                            assert (
                                check.execute(
                                    (
                                        "SELECT "
                                        "status::text "
                                        "FROM incidents"
                                    )
                                )
                                .fetchone()[0]
                                == (
                                    "FALSE_POSITIVE"
                                )
                            )

                        check.execute(
                            (
                                "UPDATE "
                                "incident_agency_"
                                "recommendations "
                                "SET "
                                "recommendation_status="
                                "'COMPLETED'"
                            )
                        )

                print(
                    "PASS",
                    shape,
                    (
                        issue
                        or "migrate+preserve"
                    ),
                    flush=True,
                )

            finally:
                admin.execute(
                    sql.SQL(
                        "DROP DATABASE {}"
                    ).format(
                        sql.Identifier(
                            name
                        )
                    )
                )


if __name__ == "__main__":
    main()