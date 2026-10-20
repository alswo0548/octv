"""CCTV 조회·감시 제어 API Repository PostgreSQL 통합 테스트.

실제 PostgreSQL transaction 안에서 다음을 검증한다.

1. CCTV 전체 목록 조회
2. CCTV 상태 summary 조회
3. region_code 필터 조회
4. CCTV 상세 조회
5. false + OFF -> 관리자 ON -> true + BASE
6. true + POST_ALERT -> 관리자 OFF -> false + OFF
7. 이미 OFF인 CCTV에 OFF 재요청
8. 존재하지 않는 CCTV 처리
9. API Response Schema 변환
10. Router 경로 등록 확인

모든 DB 변경은 마지막에 ROLLBACK한다.
"""

from __future__ import annotations

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from backend.app.config import (
    database_connect_kwargs,
)
from backend.app.cctvs import (
    repository,
    schemas,
    service,
)
from backend.app.cctvs.router import (
    router as cctv_router,
)


MISSING_CCTV_ID = (
    9_223_372_036_854_775_807
)


def _set_state(
    connection,
    cctv_id: int,
    *,
    is_monitored: bool,
    mode: str,
) -> None:
    """
    테스트용 CCTV 상태 직접 설정.

    테스트 transaction 안에서만 변경되며
    마지막에 전부 ROLLBACK된다.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE cctvs
            SET
                is_monitored = %s,
                monitored_mode =
                    %s::monitored_mode_enum
            WHERE id = %s;
            """,
            (
                is_monitored,
                mode,
                cctv_id,
            ),
        )


def _assert_state(
    row,
    *,
    expected_is_monitored: bool,
    expected_mode: str,
    label: str,
) -> None:
    """
    CCTV 감시 상태 검사.
    """

    actual_is_monitored = bool(
        row["is_monitored"]
    )

    actual_mode = str(
        row["monitored_mode"]
    )

    if (
        actual_is_monitored
        != expected_is_monitored
    ):
        raise AssertionError(
            f"{label}: "
            "is_monitored "
            f"expected="
            f"{expected_is_monitored}, "
            f"actual="
            f"{actual_is_monitored}"
        )

    if actual_mode != expected_mode:
        raise AssertionError(
            f"{label}: "
            "monitored_mode "
            f"expected={expected_mode}, "
            f"actual={actual_mode}"
        )

    print(
        f"[PASS] {label} "
        f"-> is_monitored="
        f"{actual_is_monitored} "
        f"/ mode={actual_mode}"
    )


def _find_region_target(
    rows,
):
    """
    region_code가 있는 CCTV 한 건을 찾는다.
    """

    for row in rows:
        if row["region_code"]:
            return row

    raise RuntimeError(
        "region_code가 있는 CCTV가 없습니다."
    )


def _assert_router_registration() -> None:
    """
    CCTV Router에 필요한 경로와
    HTTP Method가 등록됐는지 확인한다.
    """

    registered = set()

    route_paths = []

    for route in cctv_router.routes:
        path = getattr(
            route,
            "path",
            None,
        )

        methods = getattr(
            route,
            "methods",
            None,
        )

        if path is None:
            continue

        route_paths.append(
            path
        )

        if methods:
            for method in methods:
                registered.add(
                    (
                        method,
                        path,
                    )
                )

    expected = {
        (
            "GET",
            "/cctvs",
        ),
        (
            "GET",
            "/cctvs/summary",
        ),
        (
            "GET",
            "/cctvs/{cctv_id}",
        ),
        (
            "PATCH",
            "/cctvs/{cctv_id}/monitoring",
        ),
    }

    missing = (
        expected
        - registered
    )

    if missing:
        raise AssertionError(
            "CCTV Router에 필요한 "
            "경로가 없습니다: "
            f"{sorted(missing)}"
        )

    # /summary가 동적 /{cctv_id}보다
    # 먼저 등록되어 있는지도 확인한다.
    summary_index = route_paths.index(
        "/cctvs/summary"
    )

    detail_index = route_paths.index(
        "/cctvs/{cctv_id}"
    )

    if summary_index >= detail_index:
        raise AssertionError(
            "/cctvs/summary는 "
            "/cctvs/{cctv_id}보다 "
            "먼저 등록되어야 합니다."
        )

    print(
        "[PASS] CCTV Router 경로 등록"
    )


def main() -> None:
    print("=" * 72)

    print(
        "CCTV API POSTGRESQL "
        "INTEGRATION TEST"
    )

    print("=" * 72)

    connection = psycopg.connect(
        **database_connect_kwargs(),
        row_factory=dict_row,
    )

    try:
        # ====================================================
        # TEST 1
        # 전체 CCTV 목록 조회
        #
        # region_code=None인 실제 기본 호출을 검증한다.
        # ====================================================

        rows = repository.list_cctvs(
            connection
        )

        if not rows:
            raise AssertionError(
                "CCTV 목록이 비어 있습니다."
            )

        print(
            "[PASS] CCTV 전체 목록 조회 "
            f"-> {len(rows)}건"
        )

        target = _find_region_target(
            rows
        )

        cctv_id = int(
            target["id"]
        )

        region_code = str(
            target["region_code"]
        )

        print(
            "test CCTV:",
            cctv_id,
            "/",
            target["name"],
        )

        print(
            "region:",
            region_code,
            "/",
            target["sido_name"],
            target["sigungu_name"],
        )

        # ====================================================
        # TEST 2
        # 전체 Summary
        # ====================================================

        summary = (
            repository.get_cctv_summary(
                connection
            )
        )

        if (
            summary["total_count"]
            != len(rows)
        ):
            raise AssertionError(
                "summary total_count와 "
                "전체 CCTV 목록 개수가 "
                "일치하지 않습니다. "
                f"summary="
                f"{summary['total_count']}, "
                f"list={len(rows)}"
            )

        for key in (
            "monitored_count",
            "connected_count",
            "disconnected_count",
            "reconnecting_count",
        ):
            if summary[key] < 0:
                raise AssertionError(
                    f"{key}는 음수가 "
                    "될 수 없습니다."
                )

        print(
            "[PASS] CCTV 전체 Summary "
            f"-> total="
            f"{summary['total_count']} "
            f"/ monitored="
            f"{summary['monitored_count']} "
            f"/ connected="
            f"{summary['connected_count']} "
            f"/ disconnected="
            f"{summary['disconnected_count']} "
            f"/ reconnecting="
            f"{summary['reconnecting_count']}"
        )

        # ====================================================
        # TEST 3
        # region_code 필터
        # ====================================================

        region_rows = (
            repository.list_cctvs(
                connection,
                region_code=(
                    region_code
                ),
            )
        )

        if not region_rows:
            raise AssertionError(
                "region_code 필터 결과가 "
                "비어 있습니다."
            )

        for row in region_rows:
            if (
                str(
                    row["region_code"]
                )
                != region_code
            ):
                raise AssertionError(
                    "region_code 필터에 "
                    "다른 지역 CCTV가 "
                    "포함되었습니다."
                )

        region_summary = (
            repository.get_cctv_summary(
                connection,
                region_code=(
                    region_code
                ),
            )
        )

        if (
            region_summary[
                "total_count"
            ]
            != len(region_rows)
        ):
            raise AssertionError(
                "지역 Summary와 "
                "지역 CCTV 목록 개수가 "
                "일치하지 않습니다."
            )

        print(
            "[PASS] region_code 필터 "
            f"-> {region_code} "
            f"/ {len(region_rows)}건"
        )

        # ====================================================
        # TEST 4
        # 상세 조회
        # ====================================================

        detail = repository.get_cctv(
            connection,
            cctv_id,
        )

        if detail is None:
            raise AssertionError(
                "CCTV 상세 조회 결과가 "
                "없습니다."
            )

        if (
            int(detail["id"])
            != cctv_id
        ):
            raise AssertionError(
                "잘못된 CCTV 상세가 "
                "조회되었습니다."
            )

        print(
            "[PASS] CCTV 상세 조회"
        )

        # ====================================================
        # TEST 5
        #
        # 관리자 감시 ON
        #
        # false + OFF
        #     ->
        # true + BASE
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=False,
            mode="OFF",
        )

        before_on = repository.get_cctv(
            connection,
            cctv_id,
        )

        _assert_state(
            before_on,
            expected_is_monitored=False,
            expected_mode="OFF",
            label="관리자 ON 전 상태",
        )

        after_on = (
            repository.update_monitoring(
                connection,
                cctv_id=cctv_id,
                enabled=True,
            )
        )

        if after_on is None:
            raise AssertionError(
                "관리자 감시 ON 결과가 "
                "없습니다."
            )

        _assert_state(
            after_on,
            expected_is_monitored=True,
            expected_mode="BASE",
            label=(
                "관리자 감시 ON "
                "OFF -> BASE"
            ),
        )

        # ====================================================
        # TEST 6
        #
        # POST_ALERT 후 관리자 감시 종료
        #
        # true + POST_ALERT
        #     ->
        # false + OFF
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=True,
            mode="POST_ALERT",
        )

        before_off = repository.get_cctv(
            connection,
            cctv_id,
        )

        _assert_state(
            before_off,
            expected_is_monitored=True,
            expected_mode="POST_ALERT",
            label=(
                "관리자 종료 전 "
                "POST_ALERT"
            ),
        )

        after_off = (
            repository.update_monitoring(
                connection,
                cctv_id=cctv_id,
                enabled=False,
            )
        )

        if after_off is None:
            raise AssertionError(
                "관리자 감시 종료 결과가 "
                "없습니다."
            )

        _assert_state(
            after_off,
            expected_is_monitored=False,
            expected_mode="OFF",
            label=(
                "POST_ALERT "
                "-> 관리자 감시 종료"
            ),
        )

        # ====================================================
        # TEST 7
        # OFF -> OFF 재요청도 안전해야 한다.
        # ====================================================

        off_again = (
            repository.update_monitoring(
                connection,
                cctv_id=cctv_id,
                enabled=False,
            )
        )

        if off_again is None:
            raise AssertionError(
                "OFF 재요청 결과가 "
                "없습니다."
            )

        _assert_state(
            off_again,
            expected_is_monitored=False,
            expected_mode="OFF",
            label="OFF 재요청",
        )


        # ====================================================
        # TEST 8
        #
        # ALERT 상태에서 관리자 OFF 차단
        #
        # true + ALERT
        #     ->
        # MonitoringChangeBlockedError
        #
        # 상태는 ALERT 그대로 유지
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=True,
            mode="ALERT",
        )

        try:

            repository.update_monitoring(
                connection,
                cctv_id=cctv_id,
                enabled=False,
            )

        except (
            repository
            .MonitoringChangeBlockedError
        ) as exc:

            if (
                exc.monitored_mode
                != "ALERT"
            ):
                raise AssertionError(
                    "ALERT 차단 예외의 "
                    "monitored_mode가 잘못되었습니다. "
                    f"actual={exc.monitored_mode}"
                )

        else:

            raise AssertionError(
                "ALERT 상태 CCTV를 "
                "관리자가 OFF할 수 있으면 안 됩니다."
            )

        after_alert_block = (
            repository.get_cctv(
                connection,
                cctv_id,
            )
        )

        _assert_state(
            after_alert_block,
            expected_is_monitored=True,
            expected_mode="ALERT",
            label=(
                "ALERT 관리자 OFF 차단 후 "
                "상태 유지"
            ),
        )

        print(
            "[PASS] ALERT -> 관리자 OFF 차단"
        )

        # ====================================================
        # TEST 9
        #
        # VERIFY 상태에서 관리자 OFF 차단
        #
        # true + VERIFY
        #     ->
        # MonitoringChangeBlockedError
        #
        # 상태는 VERIFY 그대로 유지
        # ====================================================

        _set_state(
            connection,
            cctv_id,
            is_monitored=True,
            mode="VERIFY",
        )

        try:

            repository.update_monitoring(
                connection,
                cctv_id=cctv_id,
                enabled=False,
            )

        except (
            repository
            .MonitoringChangeBlockedError
        ) as exc:

            if (
                exc.monitored_mode
                != "VERIFY"
            ):
                raise AssertionError(
                    "VERIFY 차단 예외의 "
                    "monitored_mode가 잘못되었습니다. "
                    f"actual={exc.monitored_mode}"
                )

        else:

            raise AssertionError(
                "VERIFY 상태 CCTV를 "
                "관리자가 OFF할 수 있으면 안 됩니다."
            )

        after_verify_block = (
            repository.get_cctv(
                connection,
                cctv_id,
            )
        )

        _assert_state(
            after_verify_block,
            expected_is_monitored=True,
            expected_mode="VERIFY",
            label=(
                "VERIFY 관리자 OFF 차단 후 "
                "상태 유지"
            ),
        )

        print(
            "[PASS] VERIFY -> 관리자 OFF 차단"
        )

        # ====================================================
        # TEST 10
        #
        # 이미 감시 중인 CCTV에 ON 요청을 보내도
        # 시스템 monitored_mode를 BASE로 덮어쓰지 않는다.
        #
        # ALERT + ON
        #     -> ALERT 유지
        #
        # VERIFY + ON
        #     -> VERIFY 유지
        #
        # POST_ALERT + ON
        #     -> POST_ALERT 유지
        # ====================================================

        for mode in (
            "ALERT",
            "VERIFY",
            "POST_ALERT",
        ):

            _set_state(
                connection,
                cctv_id,
                is_monitored=True,
                mode=mode,
            )

            result = (
                repository.update_monitoring(
                    connection,
                    cctv_id=cctv_id,
                    enabled=True,
                )
            )

            if result is None:
                raise AssertionError(
                    "관리자 ON 상태 유지 결과가 "
                    "없습니다. "
                    f"mode={mode}"
                )

            _assert_state(
                result,
                expected_is_monitored=True,
                expected_mode=mode,
                label=(
                    f"{mode} + ON "
                    "상태 보존"
                ),
            )

        print(
            "[PASS] "
            "ALERT / VERIFY / POST_ALERT "
            "+ ON -> 현재 mode 유지"
        )


        # ====================================================
        # TEST 9
        # 존재하지 않는 CCTV
        # ====================================================

        missing_detail = (
            repository.get_cctv(
                connection,
                MISSING_CCTV_ID,
            )
        )

        if missing_detail is not None:
            raise AssertionError(
                "존재하지 않는 CCTV 상세는 "
                "None이어야 합니다."
            )

        missing_update = (
            repository.update_monitoring(
                connection,
                cctv_id=(
                    MISSING_CCTV_ID
                ),
                enabled=True,
            )
        )

        if missing_update is not None:
            raise AssertionError(
                "존재하지 않는 CCTV 변경은 "
                "None이어야 합니다."
            )

        print(
            "[PASS] 존재하지 않는 CCTV "
            "Repository 처리"
        )

        # ====================================================
        # TEST 10
        # DB row -> Pydantic Response 변환
        # ====================================================

        response = (
            service._to_cctv_response(
                detail
            )
        )

        if not isinstance(
            response,
            schemas.CctvResponse,
        ):
            raise AssertionError(
                "CctvResponse 변환에 "
                "실패했습니다."
            )

        if response.id != cctv_id:
            raise AssertionError(
                "CctvResponse ID가 "
                "일치하지 않습니다."
            )

        print(
            "[PASS] CctvResponse Schema 변환"
        )

        # ====================================================
        # TEST 11
        # Service 404
        #
        # 이 호출은 별도 connection의 읽기 조회만 수행한다.
        # ====================================================

        try:
            service.get_cctv(
                MISSING_CCTV_ID
            )

        except HTTPException as exc:
            if exc.status_code != 404:
                raise AssertionError(
                    "존재하지 않는 CCTV는 "
                    "404여야 합니다. "
                    f"actual={exc.status_code}"
                )

        else:
            raise AssertionError(
                "존재하지 않는 CCTV 조회에서 "
                "HTTPException 404가 "
                "발생하지 않았습니다."
            )

        print(
            "[PASS] Service CCTV 404 처리"
        )

        # ====================================================
        # TEST 12
        # Router 등록
        # ====================================================

        _assert_router_registration()

        print()

        print(
            "[SUCCESS] "
            "CCTV API PostgreSQL "
            "통합 테스트 정상"
        )

    finally:
        # ====================================================
        # 테스트 중 CCTV 상태 변경 전부 원상복구
        # ====================================================

        connection.rollback()
        connection.close()

        print(
            "[ROLLBACK] "
            "DB 테스트 변경사항 "
            "원상복구 완료"
        )


if __name__ == "__main__":
    main()