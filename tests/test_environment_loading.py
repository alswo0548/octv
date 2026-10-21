"""실제 키 없이 설정 우선순위와 독립 Worker/Beat의 시작 설정을 확인합니다."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentLoadingTests(unittest.TestCase):
    def run_isolated(self, root_env, backend_env, code, process_env=None):
        """필요한 Python 파일만 복사하고 가짜 .env로 새 프로세스를 실행합니다."""
        with tempfile.TemporaryDirectory(prefix="octv env ") as directory:
            project = Path(directory) / "설정 확인"
            app = project / "backend" / "app"
            app.mkdir(parents=True)
            for package in (project / "backend", app):
                (package / "__init__.py").write_text("", encoding="utf-8")
            for name in ("config.py", "workers.py", "analysis_lock.py"):
                shutil.copyfile(ROOT / "backend" / "app" / name, app / name)
            files = {
                project / ".env": root_env.encode("utf-8"),
                project / "backend" / ".env": backend_env.encode("utf-8"),
            }
            for path, contents in files.items():
                path.write_bytes(contents)

            # 사용자 환경의 키를 전달하지 않고 Python 실행에 필요한 OS 값만 유지합니다.
            environment = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR")
                if key in os.environ
            }
            dependency_paths = []
            for name in ("dotenv", "celery", "redis"):
                spec = importlib.util.find_spec(name)
                if spec and spec.origin:
                    dependency_paths.append(str(Path(spec.origin).parent.parent))
            environment.update({
                "PYTHONPATH": os.pathsep.join(dict.fromkeys([str(project), *dependency_paths])),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            })
            environment.update(process_env or {})
            outside = Path(directory) / "other cwd"
            outside.mkdir()
            guard = """
import json
import os
import sys
def deny_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise AssertionError('설정 검사에서 네트워크 호출이 발생했습니다.')
sys.addaudithook(deny_network)
"""
            result = subprocess.run(
                [sys.executable, "-c", guard + textwrap.dedent(code)],
                cwd=outside,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=20,
                check=False,
            )
            for path, contents in files.items():
                self.assertEqual(path.read_bytes(), contents, ".env 원본이 변경됐습니다.")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

    def test_process_then_backend_then_root_precedence(self):
        result = self.run_isolated(
            "ROOT_ONLY=root\nSHARED=root\nPROCESS_VALUE=root\nROUTE_API_KEY=\n",
            "BACKEND_ONLY=backend\nSHARED=backend\nPROCESS_VALUE=backend\n"
            "ROUTE_API_KEY=fake-route-key\n",
            """
            from backend.app.config import load_environment
            load_environment()
            load_environment()
            print(json.dumps({name: os.environ.get(name) for name in (
                'ROOT_ONLY', 'BACKEND_ONLY', 'SHARED', 'PROCESS_VALUE', 'ROUTE_API_KEY'
            )}))
            """,
            {"PROCESS_VALUE": "process"},
        )
        self.assertEqual(result, {
            "ROOT_ONLY": "root",
            "BACKEND_ONLY": "backend",
            "SHARED": "backend",
            "PROCESS_VALUE": "process",
            "ROUTE_API_KEY": "fake-route-key",
        })

    def test_explicit_empty_values_and_disabled_flags_are_preserved(self):
        result = self.run_isolated(
            "BACKEND_EMPTY=root\nPROCESS_EMPTY=root\nOCTV_PUSH_ENABLED=1\n",
            "BACKEND_EMPTY=\nPROCESS_EMPTY=backend\nOCTV_PUSH_ENABLED=1\nUNASSIGNED\n",
            """
            from backend.app.config import load_environment
            load_environment()
            print(json.dumps({name: os.environ.get(name) for name in (
                'BACKEND_EMPTY', 'PROCESS_EMPTY', 'OCTV_PUSH_ENABLED', 'UNASSIGNED'
            )}))
            """,
            {"PROCESS_EMPTY": "", "OCTV_PUSH_ENABLED": "0"},
        )
        self.assertEqual(result, {
            "BACKEND_EMPTY": "", "PROCESS_EMPTY": "",
            "OCTV_PUSH_ENABLED": "0", "UNASSIGNED": None,
        })

    def test_dollar_quotes_and_unicode_paths_are_literal(self):
        result = self.run_isolated(
            "TOKEN=expanded-value\n",
            "LITERAL='${TOKEN} $cash # 그대로'\n"
            "QUOTED='say \"hello\"'\n"
            "GOOGLE_APPLICATION_CREDENTIALS='C:/학생 프로젝트/키 $보관/firebase.json'\n",
            """
            from backend.app.config import load_environment
            load_environment()
            print(json.dumps({name: os.environ.get(name) for name in (
                'LITERAL', 'QUOTED', 'GOOGLE_APPLICATION_CREDENTIALS'
            )}))
            """,
        )
        self.assertEqual(result, {
            "LITERAL": "${TOKEN} $cash # 그대로",
            "QUOTED": 'say "hello"',
            "GOOGLE_APPLICATION_CREDENTIALS": "C:/학생 프로젝트/키 $보관/firebase.json",
        })

    def test_standalone_worker_and_beat_read_backend_before_initialization(self):
        result = self.run_isolated(
            "OCTV_REDIS_URL=redis://127.0.0.1:1/0\nROUTE_API_KEY=\n"
            "OCTV_PUSH_ENABLED=0\nOCTV_FIREBASE_PROJECT_ID=\n",
            "ROUTE_API_KEY=fake-route-key\nOCTV_PUSH_ENABLED=1\n"
            "OCTV_PUSH_RECOVERY_ENABLED=1\nOCTV_FIREBASE_PROJECT_ID=fake-project\n"
            "GOOGLE_APPLICATION_CREDENTIALS='C:/시험 설정/firebase.json'\n"
            "OCTV_PUSH_START_AT=2026-10-21T09:00:00+09:00\n",
            """
            from backend.app.workers import celery_app
            print(json.dumps({
                'broker': celery_app.conf.broker_url,
                'values': {name: os.environ.get(name) for name in (
                    'ROUTE_API_KEY', 'OCTV_PUSH_ENABLED', 'OCTV_PUSH_RECOVERY_ENABLED',
                    'OCTV_FIREBASE_PROJECT_ID', 'GOOGLE_APPLICATION_CREDENTIALS',
                    'OCTV_PUSH_START_AT'
                )},
                'schedule': celery_app.conf.beat_schedule,
            }))
            """,
        )
        self.assertEqual(result["broker"], "redis://127.0.0.1:1/0")
        self.assertEqual(result["values"], {
            "ROUTE_API_KEY": "fake-route-key",
            "OCTV_PUSH_ENABLED": "1",
            "OCTV_PUSH_RECOVERY_ENABLED": "1",
            "OCTV_FIREBASE_PROJECT_ID": "fake-project",
            "GOOGLE_APPLICATION_CREDENTIALS": "C:/시험 설정/firebase.json",
            "OCTV_PUSH_START_AT": "2026-10-21T09:00:00+09:00",
        })
        recovery = result["schedule"]["octv-recover-notification-pushes"]
        self.assertEqual(recovery["task"], "octv.recover_notification_pushes")
        self.assertEqual(recovery["options"]["queue"], "notifications")

    def test_process_push_disable_prevents_beat_recovery_schedule(self):
        result = self.run_isolated(
            "OCTV_REDIS_URL=redis://127.0.0.1:1/0\n",
            "OCTV_PUSH_ENABLED=1\nOCTV_PUSH_RECOVERY_ENABLED=1\n",
            """
            from backend.app.workers import celery_app
            print(json.dumps({
                'enabled': os.environ['OCTV_PUSH_ENABLED'],
                'schedule': celery_app.conf.beat_schedule,
            }))
            """,
            {"OCTV_PUSH_ENABLED": "0"},
        )
        self.assertEqual(result, {"enabled": "0", "schedule": {}})


if __name__ == "__main__":
    unittest.main()
