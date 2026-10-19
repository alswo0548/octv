"""W02~W04 역할별 접근 권한과 기관 scope를 검증한다.

검증 대상
- W02 통합관제
  CONTROL_ADMIN       -> 전체
  AGENCY_STAFF        -> 자기 기관 전달 사건
  RESPONDER           -> 자기 기관 전달 사건

- W03 사건관리
  CONTROL_ADMIN       -> 전체
  AGENCY_STAFF        -> 자기 기관 전달 사건
  RESPONDER           -> 자기 기관 전달 사건

- W03-1 추천기관/경로
  CONTROL_ADMIN       -> 전체 추천기관/경로
  AGENCY_STAFF        -> 자기 기관 전달 데이터만
  RESPONDER           -> 자기 기관 전달 데이터만

- W04 CCTV 모니터링
  CONTROL_ADMIN       -> 허용
  AGENCY_STAFF        -> 403
  RESPONDER           -> 403

실제 DB 연결은 하지 않는다.
"""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app import dependencies

from backend.app.dashboard.router import (
    router as dashboard_router,
)
from backend.app.dashboard import (
    repository as dashboard_repository,
    service as dashboard_service,
)

from backend.app.cctvs.router import (
    router as cctv_router,
)
from backend.app.cctvs import (
    service as cctv_service,
)

from backend.app.incidents import (
    repository as incident_repository,
    service as incident_service,
)

from backend.app.agencies.router import (
    router as agency_router,
)
from backend.app.agencies import (
    repository as agency_repository,
    service as agency_service,
)


class RoleAccessTests(
    unittest.TestCase
):
    def setUp(self):
        # ----------------------------------------------------
        # W02 / W03-1 / W04 Router만 붙인 작은 테스트 앱
        # ----------------------------------------------------

        self.app = FastAPI()

        self.app.include_router(
            dashboard_router,
            prefix="/api",
        )

        self.app.include_router(
            cctv_router,
            prefix="/api",
        )

        self.app.include_router(
            agency_router,
            prefix="/api",
        )

        # ----------------------------------------------------
        # 요청마다 이 dict의 현재 값을 로그인 사용자로 사용
        # ----------------------------------------------------

        self.user = {
            "id": 101,
            "email": "role-test@example.com",
            "name": "권한 테스트 사용자",
            "role": "CONTROL_ADMIN",
            "agency_id": None,
            "notification_enabled": True,
            "is_active": True,
        }

        def current_user_override():
            return self.user

        self.app.dependency_overrides[
            dependencies.get_current_user
        ] = current_user_override

        self.client = TestClient(
            self.app
        )

        self.addCleanup(
            self.client.close
        )

        self.addCleanup(
            self.app.dependency_overrides.clear
        )

        self.connection = MagicMock()

    # ========================================================
    # 사용자 변경 helper
    # ========================================================

    def set_role(
        self,
        role: str,
        agency_id: int | None,
    ):
        self.user.update(
            role=role,
            agency_id=agency_id,
            is_active=True,
        )

    @contextmanager
    def fake_connection(self):
        yield self.connection

    # ========================================================
    # W02
    # ========================================================

    def test_dashboard_router_allows_all_three_roles(
        self,
    ):
        """
        W02 페이지 자체에는 세 역할 모두 접근 가능하다.

        데이터 범위는 service/repository에서 분리한다.
        """

        response_data = {
            "summary": {
                "monitored_cctv_count": 0,
                "today_incident_count": 0,
                "connection_error_count": 0,
                "active_weather_alert_count": 0,
            },
            "incidents": {
                "items": [],
                "total": 0,
                "page": 1,
                "page_size": 5,
                "total_pages": 0,
            },
        }

        with patch.object(
            dashboard_service,
            "get_dashboard",
            return_value=response_data,
        ) as mocked:

            for (
                role,
                agency_id,
            ) in (
                (
                    "CONTROL_ADMIN",
                    None,
                ),
                (
                    "AGENCY_STAFF",
                    7,
                ),
                (
                    "RESPONDER",
                    8,
                ),
            ):
                with self.subTest(
                    role=role
                ):
                    self.set_role(
                        role,
                        agency_id,
                    )

                    mocked.reset_mock()

                    response = (
                        self.client.get(
                            "/api/dashboard"
                        )
                    )

                    self.assertEqual(
                        response.status_code,
                        200,
                    )

                    mocked.assert_called_once()

                    kwargs = (
                        mocked.call_args.kwargs
                    )

                    self.assertEqual(
                        kwargs[
                            "user"
                        ][
                            "role"
                        ],
                        role,
                    )

                    self.assertEqual(
                        kwargs[
                            "user"
                        ][
                            "agency_id"
                        ],
                        agency_id,
                    )

    def test_dashboard_role_scope(
        self,
    ):
        """
        Dashboard Service에서 role을
        실제 DB 조회 scope로 변환하는지 확인한다.
        """

        self.set_role(
            "CONTROL_ADMIN",
            None,
        )

        self.assertEqual(
            dashboard_service._role_scope(
                self.user
            ),
            (
                False,
                None,
            ),
        )

        self.set_role(
            "AGENCY_STAFF",
            7,
        )

        self.assertEqual(
            dashboard_service._role_scope(
                self.user
            ),
            (
                True,
                7,
            ),
        )

        self.set_role(
            "RESPONDER",
            8,
        )

        self.assertEqual(
            dashboard_service._role_scope(
                self.user
            ),
            (
                True,
                8,
            ),
        )

    def test_dashboard_agency_sql_requires_delivery(
        self,
    ):
        """
        기관 scope가 단순 추천(RECOMMENDED)이 아니라
        실제 DELIVERED / COMPLETED된 사건만 허용하는지 확인한다.
        """

        sql, params = (
            dashboard_repository
            ._agency_access_clause(
                incident_alias="i",
                agency_id=7,
                agency_scoped=True,
            )
        )

        self.assertIn(
            "ar.agency_id = %s",
            sql,
        )

        self.assertIn(
            "'DELIVERED'",
            sql,
        )

        self.assertIn(
            "'COMPLETED'",
            sql,
        )

        self.assertEqual(
            params,
            [7],
        )

        sql, params = (
            dashboard_repository
            ._agency_access_clause(
                incident_alias="i",
                agency_id=None,
                agency_scoped=True,
            )
        )

        self.assertEqual(
            sql,
            "FALSE",
        )

        self.assertEqual(
            params,
            [],
        )

    def test_dashboard_external_status_uses_user_scope(
        self,
    ):
        """
        사건 ID를 직접 넣어 external-status를 요청해도
        로그인 사용자 기관 scope가 적용되는지 확인한다.
        """

        with (
            patch.object(
                dashboard_service,
                "get_connection",
                self.fake_connection,
            ),
            patch.object(
                dashboard_repository,
                "get_external_status_incident",
                return_value=None,
            ) as query,
        ):

            self.set_role(
                "AGENCY_STAFF",
                7,
            )

            with self.assertRaises(
                dashboard_service
                .DashboardIncidentNotFoundError
            ):
                dashboard_service.get_external_status(
                    31,
                    user=self.user,
                )

            self.assertEqual(
                query.call_args.kwargs[
                    "agency_id"
                ],
                7,
            )

            self.assertTrue(
                query.call_args.kwargs[
                    "agency_scoped"
                ]
            )

            query.reset_mock()

            self.set_role(
                "CONTROL_ADMIN",
                None,
            )

            with self.assertRaises(
                dashboard_service
                .DashboardIncidentNotFoundError
            ):
                dashboard_service.get_external_status(
                    31,
                    user=self.user,
                )

            self.assertIsNone(
                query.call_args.kwargs[
                    "agency_id"
                ]
            )

            self.assertFalse(
                query.call_args.kwargs[
                    "agency_scoped"
                ]
            )

    # ========================================================
    # W03
    # ========================================================

    def test_incident_list_scope_for_all_roles(
        self,
    ):
        """
        기존 W03 사건 목록도
        로그인 role 기준 기관 scope를 유지하는지 확인한다.
        """

        with (
            patch.object(
                incident_service,
                "get_connection",
                self.fake_connection,
            ),
            patch.object(
                incident_repository,
                "list_incidents",
                return_value={
                    "items": [],
                    "total": 0,
                    "page": 1,
                    "page_size": 5,
                },
            ) as query,
        ):

            self.set_role(
                "CONTROL_ADMIN",
                None,
            )

            incident_service.list_incidents(
                page=1,
                page_size=5,
                filters={},
                user=self.user,
            )

            admin_filters = (
                query.call_args.args[1]
            )

            self.assertNotIn(
                "agency_id",
                admin_filters,
            )

            query.reset_mock()

            self.set_role(
                "AGENCY_STAFF",
                7,
            )

            incident_service.list_incidents(
                page=1,
                page_size=5,
                filters={},
                user=self.user,
            )

            staff_filters = (
                query.call_args.args[1]
            )

            self.assertEqual(
                staff_filters[
                    "agency_id"
                ],
                7,
            )

            query.reset_mock()

            self.set_role(
                "RESPONDER",
                8,
            )

            incident_service.list_incidents(
                page=1,
                page_size=5,
                filters={},
                user=self.user,
            )

            responder_filters = (
                query.call_args.args[1]
            )

            self.assertEqual(
                responder_filters[
                    "agency_id"
                ],
                8,
            )

    # ========================================================
    # W03-1
    # ========================================================

    def test_recommendation_scope_for_all_roles(
        self,
    ):
        """
        추천기관/경로 조회에서
        관리자는 전체,
        기관/현장은 자기 기관만 조회하도록
        repository에 agency_id를 전달하는지 확인한다.
        """

        result = {
            "incident_id": 31,
            "incident_status": "SENT",
            "items": [],
        }

        with (
            patch.object(
                agency_service,
                "get_connection",
                self.fake_connection,
            ),
            patch.object(
                agency_repository,
                "list_recommendations",
                return_value=result,
            ) as query,
        ):

            self.set_role(
                "CONTROL_ADMIN",
                None,
            )

            agency_service.list_recommendations(
                31,
                self.user,
            )

            self.assertIsNone(
                query.call_args.kwargs[
                    "agency_id"
                ]
            )

            query.reset_mock()

            self.set_role(
                "AGENCY_STAFF",
                7,
            )

            agency_service.list_recommendations(
                31,
                self.user,
            )

            self.assertEqual(
                query.call_args.kwargs[
                    "agency_id"
                ],
                7,
            )

            query.reset_mock()

            self.set_role(
                "RESPONDER",
                8,
            )

            agency_service.list_recommendations(
                31,
                self.user,
            )

            self.assertEqual(
                query.call_args.kwargs[
                    "agency_id"
                ],
                8,
            )

    def test_recommendation_scope_requires_agency(
        self,
    ):
        """
        기관/현장 계정인데 agency_id가 없다면
        잘못된 계정 상태이므로 403.
        """

        for role in (
            "AGENCY_STAFF",
            "RESPONDER",
        ):
            with self.subTest(
                role=role
            ):
                self.set_role(
                    role,
                    None,
                )

                with self.assertRaises(
                    HTTPException
                ) as error:
                    (
                        agency_service
                        ._recommendation_scope(
                            self.user
                        )
                    )

                self.assertEqual(
                    error.exception.status_code,
                    403,
                )

    def test_recommendation_repository_filters_delivered_agency(
        self,
    ):
        """
        실제 Repository SQL도
        해당 agency_id + DELIVERED/COMPLETED를 요구하는지 확인.
        """

        incident_result = MagicMock()

        incident_result.fetchone.return_value = {
            "id": 31,
            "status": "SENT",
        }

        recommendation_result = (
            MagicMock()
        )

        recommendation_result.fetchall.return_value = []

        self.connection.execute.side_effect = [
            incident_result,
            recommendation_result,
        ]

        with self.assertRaises(
            HTTPException
        ) as error:
            (
                agency_repository
                .list_recommendations(
                    self.connection,
                    31,
                    agency_id=7,
                )
            )

        self.assertEqual(
            error.exception.status_code,
            404,
        )

        recommendation_call = (
            self.connection
            .execute
            .call_args_list[1]
        )

        sql = (
            recommendation_call
            .args[0]
        )

        params = (
            recommendation_call
            .args[1]
        )

        self.assertIn(
            "ar.agency_id = %s",
            sql,
        )

        self.assertIn(
            "'DELIVERED'",
            sql,
        )

        self.assertIn(
            "'COMPLETED'",
            sql,
        )

        self.assertEqual(
            params,
            (
                31,
                7,
            ),
        )

    def test_delivery_is_admin_only(
        self,
    ):
        """
        기관 전달 버튼은 계속 CONTROL_ADMIN 전용.
        """

        request_body = {
            "selections": [
                {
                    "agency_id": 7,
                }
            ]
        }

        with patch.object(
            agency_service,
            "deliver",
            return_value={
                "incident_id": 31,
                "incident_status": "SENT",
                "items": [
                    {
                        "agency_id": 7,
                        "agency_recommendation_id": 1,
                        "status": "DELIVERED",
                        "newly_delivered": True,
                        "created_notification_count": 0,
                    }
                ],
                "created_notification_count": 0,
                "push_status": "NOT_QUEUED",
            },
        ) as deliver:

            for role in (
                "AGENCY_STAFF",
                "RESPONDER",
            ):
                with self.subTest(
                    role=role
                ):
                    self.set_role(
                        role,
                        7,
                    )

                    deliver.reset_mock()

                    response = (
                        self.client.post(
                            (
                                "/api/agencies/"
                                "incidents/31/"
                                "deliveries"
                            ),
                            json=request_body,
                        )
                    )

                    self.assertEqual(
                        response.status_code,
                        403,
                    )

                    deliver.assert_not_called()

            self.set_role(
                "CONTROL_ADMIN",
                None,
            )

            deliver.reset_mock()

            response = (
                self.client.post(
                    (
                        "/api/agencies/"
                        "incidents/31/"
                        "deliveries"
                    ),
                    json=request_body,
                )
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            deliver.assert_called_once()

    # ========================================================
    # W04
    # ========================================================

    def test_cctv_monitoring_is_admin_only(
        self,
    ):
        """
        W04의 조회/영상/감시변경 API를
        기관 담당자와 현장 담당자가 호출할 수 없어야 한다.
        """

        with (
            patch.object(
                cctv_service,
                "list_cctvs",
            ) as list_cctvs,
            patch.object(
                cctv_service,
                "get_cctv_summary",
            ) as get_summary,
            patch.object(
                cctv_service,
                "prepare_stream",
            ) as prepare_stream,
            patch.object(
                cctv_service,
                "get_cctv",
            ) as get_cctv,
            patch.object(
                cctv_service,
                "change_monitoring",
            ) as change_monitoring,
        ):

            requests = (
                (
                    "get",
                    "/api/cctvs",
                    None,
                ),
                (
                    "get",
                    "/api/cctvs/summary",
                    None,
                ),
                (
                    "post",
                    "/api/cctvs/1/stream",
                    None,
                ),
                (
                    "get",
                    "/api/cctvs/1",
                    None,
                ),
                (
                    "patch",
                    "/api/cctvs/1/monitoring",
                    {
                        "enabled": True,
                    },
                ),
            )

            for role in (
                "AGENCY_STAFF",
                "RESPONDER",
            ):
                self.set_role(
                    role,
                    7,
                )

                for (
                    method,
                    path,
                    body,
                ) in requests:
                    with self.subTest(
                        role=role,
                        path=path,
                    ):
                        response = (
                            self.client.request(
                                method,
                                path,
                                json=body,
                            )
                        )

                        self.assertEqual(
                            response.status_code,
                            403,
                        )

            for mocked in (
                list_cctvs,
                get_summary,
                prepare_stream,
                get_cctv,
                change_monitoring,
            ):
                mocked.assert_not_called()

    def test_cctv_monitoring_admin_can_enter(
        self,
    ):
        """
        CONTROL_ADMIN은 W04에 접근할 수 있어야 한다.
        """

        self.set_role(
            "CONTROL_ADMIN",
            None,
        )

        with patch.object(
            cctv_service,
            "list_cctvs",
            return_value=[],
        ) as query:

            response = (
                self.client.get(
                    "/api/cctvs"
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            response.json(),
            [],
        )

        query.assert_called_once()


if __name__ == "__main__":
    unittest.main()