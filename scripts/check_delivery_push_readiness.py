"""Read-only, secret-safe preflight for OCTV agency delivery -> Android FCM.

Run from the project root:
  .venv\\Scripts\\python -X utf8 -m scripts.check_delivery_push_readiness

Does NOT connect to DB/Redis/Firebase, register devices, send push, or edit .env.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def _file_env(path: Path) -> dict[str, str]:
    return {key: value for key, value in dotenv_values(path, interpolate=False).items()
            if value is not None}


def _duplicate_keys(path: Path) -> list[str]:
    if not path.exists():
        return []
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        if match:
            key = match.group(1)
            if key in seen:
                duplicates.add(key)
            seen.add(key)
    return sorted(duplicates)


def _credential_state(root: Path, raw: str, platform: str) -> str:
    if not raw:
        return "NOT_CONFIGURED"
    # ZIP inspections on Linux cannot verify the Windows user's local drive.
    if platform != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
        return "CHECK_ON_WINDOWS"
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = root / path
    return "FILE_PRESENT" if path.is_file() else "FILE_NOT_FOUND"


def _timestamp_state(raw: str) -> str:
    if not raw:
        return "NOT_CONFIGURED"
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            return "TIMEZONE_REQUIRED"
        if value.astimezone(timezone.utc) > datetime.now(timezone.utc):
            return "FUTURE_START"
        return "VALID"
    except (TypeError, ValueError, OverflowError):
        return "INVALID"


def _url_state(url: str, allow_cleartext: str) -> str:
    if not url:
        return "NOT_CONFIGURED"
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "INVALID_URL"
        if parts.path not in ("", "/"):
            return "INVALID_URL"
        if parts.hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return "ANDROID_LOOPBACK_NOT_PC"
        if parts.username or parts.password or parts.query or parts.fragment:
            return "INVALID_URL"
        if parts.scheme == "http" and allow_cleartext != "1":
            return "HTTP_BLOCKED_BY_ANDROID_CONFIG"
        return "READY_FOR_CONNECTIVITY_TEST"  # Not a network reachability claim.
    except ValueError:
        return "INVALID_URL"


def _android_firebase_state(root: Path, mobile: dict[str, str], backend: dict[str, str]) -> str:
    raw = (mobile.get("OCTV_ANDROID_GOOGLE_SERVICES_FILE") or "./google-services.json").strip()
    # Cloud EAS file variables can supply files that do not exist on this machine.
    raw = os.environ.get("GOOGLE_SERVICES_JSON", "").strip() or raw
    path = Path(raw)
    if not path.is_absolute():
        path = root / "frontend" / "mobile" / path
    if not path.is_file():
        return "CLIENT_FILE_NOT_FOUND_LOCALLY"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or "private_key" in value or value.get("type") == "service_account":
            return "NOT_ANDROID_CLIENT_FILE"
        clients = value.get("client", [])
        if not isinstance(clients, list):
            return "INVALID_CLIENT_FILE"
        package = mobile.get("OCTV_ANDROID_PACKAGE") or "com.octv.mobile"
        if not any(isinstance(client, dict) and
                   client.get("client_info", {}).get("android_client_info", {}).get("package_name") == package
                   for client in clients):
            return "ANDROID_PACKAGE_MISMATCH"
        project = (value.get("project_info") or {}).get("project_id")
        if not project or project != backend.get("OCTV_FIREBASE_PROJECT_ID"):
            return "FIREBASE_PROJECT_MISMATCH"
        return "CLIENT_CONFIG_MATCHED"
    except (OSError, ValueError, TypeError, AttributeError):
        return "INVALID_CLIENT_FILE"


def audit(root: Path = ROOT, *, platform: str | None = None,
          process_env: dict[str, str] | None = None) -> dict:
    root = Path(root)
    platform = platform if platform is not None else os.name
    # Respect the existing backend/app/config.py precedence (process > backend > root).
    root_env = _file_env(root / ".env")
    backend_file = _file_env(root / "backend" / ".env")
    mobile_file = _file_env(root / "frontend" / "mobile" / ".env")
    process_env = dict(os.environ if process_env is None else process_env)
    backend = {**root_env, **backend_file, **{
        key: value for key, value in process_env.items() if key in (root_env | backend_file)
    }}
    mobile = {**mobile_file, **{
        key: value for key, value in process_env.items() if key in mobile_file
    }}
    push_enabled = backend.get("OCTV_PUSH_ENABLED") == "1"
    recovery_enabled = backend.get("OCTV_PUSH_RECOVERY_ENABLED") == "1"
    state = {
        "push": "ENABLED" if push_enabled else "OFF_REQUIRES_TEST_APPROVAL",
        "push_start": _timestamp_state(backend.get("OCTV_PUSH_START_AT", "").strip()),
        "push_recovery": "ENABLED_NEEDS_SINGLE_BEAT" if recovery_enabled else "OFF_OPTIONAL_FOR_FIRST_TEST",
        "firebase_project": "CONFIGURED" if backend.get("OCTV_FIREBASE_PROJECT_ID", "").strip() else "NOT_CONFIGURED",
        "firebase_credentials": _credential_state(
            root, backend.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip(), platform),
        "firebase_android_client": _android_firebase_state(root, mobile, backend),
        "mobile_api": _url_state(mobile.get("EXPO_PUBLIC_API_BASE_URL", "").strip(),
                                 mobile.get("OCTV_ANDROID_ALLOW_HTTP", "0").strip()),
        "redis_environment_consistency": ("MATCHED" if root_env.get("OCTV_REDIS_URL") and
                                           root_env.get("OCTV_REDIS_URL") == backend_file.get("OCTV_REDIS_URL")
                                           else "MISSING_OR_DIFFERENT"),
        "required_packages": {
            name: "INSTALLED" if importlib.util.find_spec(name) else "NOT_INSTALLED"
            for name in ("celery", "redis", "firebase_admin", "psycopg")
        },
        "duplicate_backend_env_keys": _duplicate_keys(root / "backend" / ".env"),
    }
    blocking = []
    if state["firebase_project"] != "CONFIGURED":
        blocking.append("FIREBASE_PROJECT_REQUIRED")
    if state["firebase_credentials"] in ("NOT_CONFIGURED", "FILE_NOT_FOUND"):
        blocking.append("SERVER_CREDENTIALS_REQUIRED")
    if state["firebase_android_client"] != "CLIENT_CONFIG_MATCHED":
        blocking.append("ANDROID_CLIENT_CONFIG_REQUIRED")
    if state["mobile_api"] != "READY_FOR_CONNECTIVITY_TEST":
        blocking.append("ANDROID_API_CONFIG_REQUIRED")
    if state["redis_environment_consistency"] != "MATCHED":
        blocking.append("REDIS_ENV_MISMATCH")
    for package, present in state["required_packages"].items():
        if present != "INSTALLED":
            blocking.append("MISSING_PYTHON_PACKAGE_" + package.upper())
    # These gates are deliberately not changed here: a real delivery may target real users.
    approval_gates = []
    if not push_enabled:
        approval_gates.append("TEST_RECIPIENT_AND_PUSH_ENABLE_APPROVAL")
    if state["push_start"] != "VALID":
        approval_gates.append("PUSH_START_TIMESTAMP_REVIEW")
    return {
        "mode": "READ_ONLY_NO_NETWORK_NO_SEND",
        "settings": state,
        "local_blockers": blocking,
        "approval_gates": approval_gates,
        "runtime_checks_not_performed": [
            "ACTIVE_WORKER_QUEUE", "DB_TEST_RECIPIENT", "REDIS_DEVICE_TOKEN",
            "FIREBASE_AUTHENTICATION", "ANDROID_APK_AND_RECEIPT",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="OCTV repository root")
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.root), ensure_ascii=False, indent=2))
    except Exception:
        # Credential paths, env values, and raw exceptions must never enter the diagnostic output.
        print(json.dumps({"mode": "READ_ONLY_NO_NETWORK_NO_SEND", "error": "SETUP_READ_FAILED"}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
