"""Opt-in MediaMTX watchdog for *monitored* UTIC streams.

This module does not change monitoring state, CCTV capture/YOLO, or notifications.
A sick stream can be repaired without modifying other CCTV paths.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any

import requests

from backend.app.cctvs import repository, streaming
from backend.app.db.session import get_connection

log = logging.getLogger(__name__)

FAILURE_THRESHOLD = 3
POLL_SECONDS = 30
PATCH_SETTLE_SECONDS = 10
RECREATE_SETTLE_SECONDS = 15
COOLDOWN_SECONDS = 600
LOCK_SECONDS = 180
MAX_ATTEMPTS_PER_HOUR = 2
# Brief proof that this exact CCTV was an actively managed warm path.
# Redis holds the external CCTV ID, never the source URL or credentials.
WARM_SEEN_TTL_SECONDS = 600
KEY_PREFIX = "octv:cctv:stream-recovery"

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _keys(cctv_id: int) -> dict[str, str]:
    prefix = f"{KEY_PREFIX}:{cctv_id}"
    return {suffix: f"{prefix}:{suffix}" for suffix in ("lock", "cooldown", "attempts", "backup", "warm_seen")}


def _monitored_targets() -> list[tuple[int, str]]:
    """Read live DB policy each cycle; no hard-coded device IDs."""
    with get_connection() as connection:
        rows = repository.list_monitored_utic_cctvs(connection)
    return [
        (int(row["id"]), str(row["external_cctv_id"]))
        for row in rows
        if row["external_cctv_id"]
        and str(row["monitored_mode"]).upper() != "OFF"
    ]


def _still_monitored(cctv_id: int, external_cctv_id: str) -> bool:
    """Recheck after acquiring lease and before destructive operations."""
    with get_connection() as connection:
        row = repository.get_cctv(connection, cctv_id)
    return bool(
        row
        and row["is_monitored"]
        and str(row["provider"]).upper() == "UTIC"
        and str(row["external_cctv_id"]) == external_cctv_id
        and str(row["monitored_mode"]).upper() != "OFF"
    )


def _ready(state: dict[str, Any] | None) -> bool:
    return bool(
        state
        and state.get("online") is True
        and state.get("ready") is True
        and state.get("available") is True
        and (state.get("tracks") or [])
    )


def _path_state(path: str) -> dict[str, Any] | None:
    return streaming._get_mediamtx_runtime_path(path)


def _path_config(path: str) -> dict[str, Any] | None:
    return streaming._get_mediamtx_path_config(path)


def _managed_warm_path(config: dict[str, Any] | None) -> bool:
    """An idle/on-demand or missing path must never be started by the watchdog."""
    return bool(config and config.get("source") and config.get("sourceOnDemand") is False)


def _missing_path_recreate_enabled() -> bool:
    """Extra opt-in: a missing path is different from an unready existing path."""
    return os.getenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "0").strip() == "1"


def _add_path(path: str, config: dict[str, Any]) -> None:
    payload = {name: value for name, value in config.items() if name != "name"}
    response = requests.post(
        streaming._config_path_url("add", path),
        json=payload,
        timeout=streaming.MEDIAMTX_REQUEST_TIMEOUT_SEC,
    )
    if response.status_code != 200:
        raise RuntimeError(f"MediaMTX add status={response.status_code}")


def _recreate_path(path: str, desired: dict[str, Any], backup: dict[str, Any]) -> None:
    """DELETE/ADD only this path; try original config if ADD fails."""
    response = requests.delete(
        streaming._config_path_url("delete", path),
        timeout=streaming.MEDIAMTX_REQUEST_TIMEOUT_SEC,
    )
    if response.status_code != 200:
        raise RuntimeError(f"MediaMTX delete status={response.status_code}")

    try:
        _add_path(path, desired)
    except Exception:
        # If ADD timed out but succeeded, do not overwrite a live config.
        try:
            if _path_config(path) is None:
                _add_path(path, backup)
                log.warning("CCTV %s original path config restored", path)
        except Exception as error:
            log.error("CCTV %s config restore failed (%s)", path, type(error).__name__)
        raise


class StreamRecoveryWatchdog:
    """One process, per-CCTV health counters + distributed Redis leases."""

    def __init__(self, redis_client: Any, *, sleep: Any = time.sleep) -> None:
        self.redis = redis_client
        self.sleep = sleep
        self.consecutive_failures: dict[int, int] = {}

    def step(self) -> dict[int, str]:
        """Check only currently monitored UTIC paths (no DB writes)."""
        try:
            targets = _monitored_targets()
        except Exception as error:
            log.warning("CCTV recovery DB list unavailable (%s)", type(error).__name__)
            self.consecutive_failures.clear()
            return {}

        active_ids = {cctv_id for cctv_id, _ in targets}
        self.consecutive_failures = {
            cctv_id: count for cctv_id, count in self.consecutive_failures.items()
            if cctv_id in active_ids
        }
        statuses = {}
        for cctv_id, external_id in targets:
            try:
                statuses[cctv_id] = self._check_one(cctv_id, external_id)
            except Exception as error:
                self.consecutive_failures.pop(cctv_id, None)
                log.warning("CCTV %s check skipped (%s)", cctv_id, type(error).__name__)
                statuses[cctv_id] = "check-error"
        return statuses

    def _check_one(self, cctv_id: int, external_id: str) -> str:
        path = f"cctv-{cctv_id}"
        state = _path_state(path)
        keys = _keys(cctv_id)
        if _ready(state):
            # A ready stream stays healthy even if the config API briefly fails.
            # Only observed warm paths may later be recreated if config disappears.
            try:
                current = _path_config(path)
                if _managed_warm_path(current):
                    self.redis.set(keys["warm_seen"], external_id, ex=WARM_SEEN_TTL_SECONDS)
                elif current is not None:
                    self.redis.set(keys["warm_seen"], "-", ex=WARM_SEEN_TTL_SECONDS)
            except Exception as error:
                log.debug("CCTV %s warm proof unavailable (%s)", cctv_id, type(error).__name__)
            self.consecutive_failures.pop(cctv_id, None)
            return "healthy"

        current = _path_config(path)
        if _managed_warm_path(current):
            self.redis.set(keys["warm_seen"], external_id, ex=WARM_SEEN_TTL_SECONDS)
        elif current is not None:
            # An explicit on-demand/non-warm path must never be overwritten.
            self.redis.set(keys["warm_seen"], "-", ex=WARM_SEEN_TTL_SECONDS)
            self.consecutive_failures.pop(cctv_id, None)
            return "not-warm-path"
        elif not (
            _missing_path_recreate_enabled()
            and self.redis.get(keys["warm_seen"]) == external_id
        ):
            # Missing path with no recent proven warm state: leave it untouched.
            self.consecutive_failures.pop(cctv_id, None)
            return "not-warm-path"

        failures = self.consecutive_failures.get(cctv_id, 0) + 1
        self.consecutive_failures[cctv_id] = failures
        if failures < FAILURE_THRESHOLD:
            return "observing"

        self.consecutive_failures.pop(cctv_id, None)
        return self._attempt_recovery(cctv_id, external_id)

    def _attempt_recovery(self, cctv_id: int, external_id: str) -> str:
        path = f"cctv-{cctv_id}"
        keys = _keys(cctv_id)
        # Fail closed if Redis is down; never repair without a lease.
        if self.redis.exists(keys["cooldown"]):
            return "cooldown"
        token = secrets.token_hex(16)
        if not self.redis.set(keys["lock"], token, nx=True, ex=LOCK_SECONDS):
            return "locked"

        attempted = False
        try:
            if not _still_monitored(cctv_id, external_id):
                return "monitoring-off"
            if _ready(_path_state(path)):
                return "already-ready"
            original = _path_config(path)
            missing_with_proof = (
                original is None
                and _missing_path_recreate_enabled()
                and self.redis.get(keys["warm_seen"]) == external_id
            )
            if not missing_with_proof and not _managed_warm_path(original):
                return "not-warm-path"

            if int(self.redis.get(keys["attempts"]) or 0) >= MAX_ATTEMPTS_PER_HOUR:
                return "hourly-limit"

            # Validate new source *before* touching the existing MediaMTX path.
            stream_url, _ = streaming.get_utic_stream_url(external_id)
            source_url, fingerprint = streaming._build_mediamtx_source(stream_url)
            if not source_url:
                return "empty-source"

            attempt_number = self.redis.incr(keys["attempts"])
            if attempt_number == 1:
                self.redis.expire(keys["attempts"], 3600)
            attempted = True

            if missing_with_proof:
                # A missing path is only ADDed; never DELETE an unrelated path.
                # A competing API request may register a path first: do not PATCH it.
                if not _still_monitored(cctv_id, external_id):
                    return "monitoring-off"
                if _path_config(path) is not None:
                    return "config-changed"
                payload = {
                    "source": source_url,
                    "sourceOnDemand": False,
                    "sourceOnDemandStartTimeout": streaming.SOURCE_ON_DEMAND_START_TIMEOUT,
                    "sourceOnDemandCloseAfter": streaming.SOURCE_ON_DEMAND_CLOSE_AFTER,
                    "sourceFingerprint": fingerprint,
                }
                _add_path(path, payload)
                self.sleep(RECREATE_SETTLE_SECONDS)
                if _ready(_path_state(path)):
                    log.info("CCTV %s missing warm path restored", cctv_id)
                    return "missing-path-restored"
                return "missing-path-added-waiting"

            streaming._upsert_mediamtx_path(
                path_name=path,
                source_url=source_url,
                source_fingerprint=fingerprint,
                keep_warm=True,
                force_reload=True,
            )
            self.sleep(PATCH_SETTLE_SECONDS)
            if _ready(_path_state(path)):
                log.info("CCTV %s recovered via PATCH", cctv_id)
                return "patch-recovered"

            if not _still_monitored(cctv_id, external_id) or _ready(_path_state(path)):
                return "state-changed"
            desired = _path_config(path)
            if not _managed_warm_path(desired):
                return "not-warm-path"
            if desired.get("source") != source_url:
                return "config-changed"

            # Keep original configuration in Redis for emergency rollback.
            # It can contain source credentials; do not log or export it.
            saved = self.redis.set(keys["backup"], json.dumps(original), ex=86400)
            if not saved:
                return "backup-failed"
            if not _still_monitored(cctv_id, external_id) or _ready(_path_state(path)):
                return "state-changed"
            if _path_config(path) != desired:
                return "config-changed"

            _recreate_path(path, desired, original)
            self.sleep(RECREATE_SETTLE_SECONDS)
            if _ready(_path_state(path)):
                log.info("CCTV %s recovered via path recreation", cctv_id)
                return "recreated-recovered"
            log.warning("CCTV %s was recreated; upstream not ready", cctv_id)
            return "recreated-waiting"
        finally:
            if attempted:
                try:
                    self.redis.set(keys["cooldown"], "1", ex=COOLDOWN_SECONDS)
                except Exception:
                    log.error("CCTV %s cooldown write failed", cctv_id)
            try:
                self.redis.eval(_RELEASE_LOCK_SCRIPT, 1, keys["lock"], token)
            except Exception:
                log.error("CCTV %s Redis lease release failed; TTL will expire", cctv_id)
