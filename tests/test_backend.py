"""실제 HTTP 기동 검사. 기능 구현 시 해당 미구현 검사를 기능 테스트로 교체하세요."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler


class BackendScaffoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 외부 시스템에 접속하지 않고 임시 localhost 포트에서 서버를 검사합니다.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.url = f"http://127.0.0.1:{port}"
        cls.client = build_opener(ProxyHandler({}))
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
            cwd=Path(__file__).resolve().parents[1],
        )
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError("개발 서버가 시작 중 종료되었습니다.")
            try:
                with cls.client.open(cls.url + "/health", timeout=1):
                    return
            except URLError:
                time.sleep(0.1)
        raise RuntimeError("개발 서버 기동 시간 초과")

    @classmethod
    def stop_server(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait()

    def request(self, path, method="GET", payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            self.url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = self.client.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_health_does_not_claim_database_connection(self):
        status, body = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["database"], "not_checked")

    def test_login_and_email_check_do_not_fake_success(self):
        for path, body in [
            ("/api/auth/login", {"email": "test@example.com", "password": "test-only"}),
            ("/api/auth/email-check", {"email": "test@example.com"}),
        ]:
            with self.subTest(path=path):
                status, result = self.request(path, "POST", body)
                self.assertEqual(status, 501)
                self.assertNotIn("test-only", json.dumps(result))

    def test_monitoring_and_delivery_do_not_claim_state_change(self):
        cases = [
            ("/api/cctvs/1/monitoring", "PATCH", {"enabled": False}),
            (
                "/api/agencies/incidents/1/deliveries",
                "POST",
                {"selections": [{"agency_id": 1, "route_candidate_id": 1}]},
            ),
            (
                "/api/support-requests/incidents/1",
                "POST",
                {"support_type": "OTHER", "request_content": "개발 환경 확인"},
            ),
        ]
        for path, method, body in cases:
            with self.subTest(path=path):
                self.assertEqual(self.request(path, method, body)[0], 501)

    def test_api_documentation_contains_all_domains(self):
        status, api = self.request("/openapi.json")
        self.assertEqual(status, 200)
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
            self.assertTrue(any(p.startswith("/api/" + domain) for p in api["paths"]))


if __name__ == "__main__":
    unittest.main()
