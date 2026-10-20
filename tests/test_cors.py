"""CORS와 기존 로그인→JWT→사용자 조회 연결. DB만 Mock이며 실계정 시험은 별도입니다."""

import importlib
import os
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import bcrypt
from fastapi.testclient import TestClient

from backend.app import config


class CorsConfigTests(unittest.TestCase):
    def test_reads_backend_env_directly_without_mutating_environment(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend" / ".env").write_text(
                "OCTV_CORS_ALLOWED_ORIGINS=http://localhost:8081, https://app.example.com\n",
                encoding="utf-8",
            )
            with patch.object(config, "ROOT", root), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(config.cors_allowed_origins(), [
                    "http://localhost:8081", "https://app.example.com",
                ])
                self.assertNotIn("OCTV_CORS_ALLOWED_ORIGINS", os.environ)
                with patch.dict(os.environ, {"OCTV_CORS_ALLOWED_ORIGINS": ""}):
                    self.assertEqual(config.cors_allowed_origins(), [])

    def test_deduplicates_explicit_origins_and_environment_takes_precedence(self):
        with patch.dict(os.environ, {
            "OCTV_CORS_ALLOWED_ORIGINS": "http://127.0.0.1:8081, http://127.0.0.1:8081",
        }):
            self.assertEqual(config.cors_allowed_origins(), ["http://127.0.0.1:8081"])

    def test_rejects_wildcards_paths_and_non_origins(self):
        for value in ("*", "https://*.example.com", "null", "ftp://example.com",
                      "https://example.com/", "https://example.com/api",
                      "https://example.com?q=1", "https://example.com#part",
                      "https://user:pass@example.com", "http://localhost:70000"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "OCTV_CORS_ALLOWED_ORIGINS": value,
            }), self.assertRaises(ValueError):
                config.cors_allowed_origins()


class CorsHttpTests(unittest.TestCase):
    origin = "http://localhost:8081"

    def setUp(self):
        self.environment = patch.dict(os.environ, {
            "OCTV_CORS_ALLOWED_ORIGINS": self.origin,
            "JWT_SECRET": "TEST_ONLY_" + "x" * 48,
        })
        self.environment.start()
        from backend.app import main
        self.main = main
        self.client = TestClient(importlib.reload(main).app)

    def tearDown(self):
        self.client.close()
        self.environment.stop()
        importlib.reload(self.main)

    def preflight(self, path, method, origin=None):
        return self.client.options(path, headers={
            "Origin": origin or self.origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "authorization,content-type",
        })

    def test_allowed_preflights_for_login_and_me(self):
        for path, method in (("/api/auth/login", "POST"), ("/api/auth/me", "GET")):
            with self.subTest(path=path):
                response = self.preflight(path, method)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["access-control-allow-origin"], self.origin)
                self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_unlisted_origin_is_rejected(self):
        response = self.preflight("/api/auth/login", "POST", "http://unlisted.example:8081")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_unlisted_method_is_rejected(self):
        self.assertEqual(self.preflight("/api/auth/login", "TRACE").status_code, 400)

    def test_existing_login_and_me_with_mock_database(self):
        password = "LocalTest9!"
        user = {
            "id": 1, "email": "test@example.com", "name": "검증 계정",
            "role": "AGENCY_STAFF", "agency_id": 9, "is_active": True,
            "notification_enabled": True,
            "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode(),
        }
        # 로그인 처리·비밀번호 검증·JWT 발급/해독은 원래 코드를 그대로 실행합니다.
        with patch("backend.app.auth.service.get_connection", return_value=nullcontext(object())), patch(
            "backend.app.dependencies.get_connection", return_value=nullcontext(object())
        ), patch("backend.app.auth.repository.find_user_by_email", return_value=user), patch(
            "backend.app.auth.repository.find_user_by_id", return_value=user
        ):
            response = self.client.post("/api/auth/login", headers={"Origin": self.origin},
                                        json={"email": user["email"], "password": password})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], self.origin)
            token = response.json()["access_token"]
            me = self.client.get("/api/auth/me", headers={
                "Origin": self.origin, "Authorization": "Bearer " + token,
            })
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["agency_id"], 9)
            self.assertEqual(me.headers["access-control-allow-origin"], self.origin)
            bad = self.client.post("/api/auth/login", headers={"Origin": self.origin},
                                   json={"email": user["email"], "password": "wrong"})
            self.assertEqual(bad.status_code, 401)
            self.assertEqual(bad.headers["access-control-allow-origin"], self.origin)

    def test_cors_does_not_bypass_authentication(self):
        response = self.client.get("/api/auth/me", headers={"Origin": self.origin})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["access-control-allow-origin"], self.origin)


if __name__ == "__main__":
    unittest.main()
