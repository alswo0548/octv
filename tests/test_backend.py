"""실제 HTTP 기동 및 백엔드 기본 계약 검사."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.request import (
    Request,
    build_opener,
    ProxyHandler,
)


class BackendScaffoldTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        """
        외부 시스템에 접속하지 않고
        임시 localhost 포트에서 서버를 검사한다.
        """

        with socket.socket() as sock:
            sock.bind(
                (
                    "127.0.0.1",
                    0,
                )
            )

            port = (
                sock.getsockname()[1]
            )

        cls.url = (
            f"http://127.0.0.1:{port}"
        )

        cls.client = build_opener(
            ProxyHandler({})
        )

        cls.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "error",
            ],
            cwd=(
                Path(__file__)
                .resolve()
                .parents[1]
            ),
        )

        cls.addClassCleanup(
            cls.stop_server
        )

        deadline = (
            time.monotonic()
            + 15
        )

        while (
            time.monotonic()
            < deadline
        ):
            if (
                cls.process.poll()
                is not None
            ):
                raise RuntimeError(
                    "개발 서버가 시작 중 "
                    "종료되었습니다."
                )

            try:
                with cls.client.open(
                    cls.url + "/health",
                    timeout=1,
                ):
                    return

            except URLError:
                time.sleep(
                    0.1
                )

        raise RuntimeError(
            "개발 서버 기동 시간 초과"
        )

    @classmethod
    def stop_server(cls):

        cls.process.terminate()

        try:
            cls.process.wait(
                timeout=5
            )

        except subprocess.TimeoutExpired:

            cls.process.kill()
            cls.process.wait()

    def request(
        self,
        path,
        method="GET",
        payload=None,
    ):
        data = (
            None
            if payload is None
            else json.dumps(
                payload
            ).encode()
        )

        request = Request(
            self.url + path,
            data=data,
            method=method,
            headers={
                "Content-Type":
                    "application/json"
            },
        )

        try:
            response = (
                self.client.open(
                    request,
                    timeout=5,
                )
            )

        except HTTPError as error:
            response = error

        with response:
            try:
                body = json.load(
                    response
                )

            except json.JSONDecodeError:
                body = {}

            return (
                response.status,
                body,
            )

    def openapi(self):

        status, body = self.request(
            "/openapi.json"
        )

        self.assertEqual(
            status,
            200,
        )

        return body

    def test_health_does_not_claim_database_connection(
        self,
    ):
        status, body = self.request(
            "/health"
        )

        self.assertEqual(
            status,
            200,
        )

        self.assertEqual(
            body["database"],
            "not_checked",
        )

    def test_auth_routes_are_registered(
        self,
    ):
        """
        Backend smoke test에는
        DB 서버가 없으므로 실제 로그인 요청 대신
        OpenAPI에 구현 Route가 등록됐는지 확인한다.
        """

        api = self.openapi()

        paths = api["paths"]

        self.assertIn(
            "/api/auth/login",
            paths,
        )

        self.assertIn(
            "post",
            paths[
                "/api/auth/login"
            ],
        )

        self.assertIn(
            "/api/auth/email-check",
            paths,
        )

        self.assertIn(
            "post",
            paths[
                "/api/auth/email-check"
            ],
        )

    def test_unimplemented_routes_do_not_claim_state_change(
        self,
    ):
        """
        아직 미구현인 API가
        구현 완료 상태를 반환하지 않는지 확인한다.
        """

        cases = [
            (
                (
                    "/api/support-requests/"
                    "incidents/1"
                ),
                "POST",
                {
                    "support_type":
                        "OTHER",

                    "request_content":
                        "개발 환경 확인",
                },
            ),
        ]

        for (
            path,
            method,
            body,
        ) in cases:

            with self.subTest(
                path=path
            ):
                status, _ = (
                    self.request(
                        path,
                        method,
                        body,
                    )
                )

                self.assertEqual(
                    status,
                    501,
                )

    def test_cctv_routes_require_authentication(
        self,
    ):
        """
        구현된 CCTV 상태 변경 및
        실시간 Stream 준비 API는
        로그인하지 않은 요청을 거부해야 한다.
        """

        cases = [
            (
                (
                    "/api/cctvs/1/"
                    "monitoring"
                ),
                "PATCH",
                {
                    "enabled":
                        False
                },
            ),
            (
                (
                    "/api/cctvs/1/"
                    "stream"
                ),
                "POST",
                None,
            ),
        ]

        for (
            path,
            method,
            body,
        ) in cases:

            with self.subTest(
                path=path
            ):
                status, _ = (
                    self.request(
                        path,
                        method,
                        body,
                    )
                )

                self.assertEqual(
                    status,
                    401,
                )

    def test_delivery_requires_authentication(
        self,
    ):
        status, _ = self.request(
            (
                "/api/agencies/"
                "incidents/1/"
                "deliveries"
            ),
            "POST",
            {
                "selections": [
                    {
                        "agency_id":
                            1,

                        "route_candidate_id":
                            1,
                    }
                ]
            },
        )

        self.assertEqual(
            status,
            401,
        )

    def test_api_documentation_contains_all_domains(
        self,
    ):
        api = self.openapi()

        for domain in [
            "auth",
            "cctvs",
            "incidents",
            "agencies",
            "routes",
            "notifications",
            "support-requests",
            "settings",
            "stats",
        ]:

            self.assertTrue(
                any(
                    path.startswith(
                        "/api/"
                        + domain
                    )
                    for path
                    in api["paths"]
                )
            )


if __name__ == "__main__":
    unittest.main()