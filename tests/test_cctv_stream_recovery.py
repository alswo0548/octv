"""Mock-only checks: no live DB, Redis, MediaMTX, or UTIC requests."""
from __future__ import annotations

import pytest
from backend.app.cctvs import stream_recovery as recovery


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expiries = {}

    def exists(self, key):
        return key in self.data

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = str(value)
        if ex is not None:
            self.expiries[key] = ex
        return True

    def incr(self, key):
        n = int(self.data.get(key, 0)) + 1
        self.data[key] = str(n)
        return n

    def expire(self, key, seconds):
        self.expiries[key] = seconds
        return True

    def eval(self, _script, _num_keys, key, token):
        if self.data.get(key) == token:
            del self.data[key]
            return 1
        return 0


READY = {"online": True, "ready": True, "available": True, "tracks": ["H264"]}
BROKEN = {"online": True, "ready": False, "available": False, "tracks": []}
OFFLINE = {"online": False, "ready": False, "available": False, "tracks": []}
WARM = {"source": "https://example.test/old", "sourceOnDemand": False, "sourceFingerprint": "hash"}


def setup(monkeypatch, *, ids=((9, "E910006"), (10, "E910012")), states=None, config=None):
    states = states if states is not None else {9: BROKEN, 10: READY}
    config = config if config is not None else {9: dict(WARM), 10: dict(WARM)}
    monkeypatch.setattr(recovery, "_monitored_targets", lambda: list(ids))
    monkeypatch.setattr(recovery, "_still_monitored", lambda _id, _external: True)
    monkeypatch.setattr(recovery, "_path_state", lambda path: states[int(path[5:])])
    monkeypatch.setattr(recovery, "_path_config", lambda path: config.get(int(path[5:])))
    monkeypatch.setattr(recovery.streaming, "get_utic_stream_url", lambda _eid: ("https://example.test/old", {}))
    monkeypatch.setattr(recovery.streaming, "_build_mediamtx_source", lambda url: (url, "hash"))
    return states, config


def arm_repair(monkeypatch, *, ids=((9, "E910006"), (10, "E910012")), states=None, patch_succeeds=False):
    states, config = setup(monkeypatch, ids=ids, states=states)
    calls = []

    def patch(**kwargs):
        cctv_id = int(kwargs["path_name"][5:])
        calls.append(("patch", cctv_id))
        if patch_succeeds:
            states[cctv_id] = READY

    def recreate(path, _desired, _backup):
        cctv_id = int(path[5:])
        calls.append(("recreate", cctv_id))
        states[cctv_id] = READY

    monkeypatch.setattr(recovery.streaming, "_upsert_mediamtx_path", patch)
    monkeypatch.setattr(recovery, "_recreate_path", recreate)
    return calls


def test_healthy_cctv_never_changes(monkeypatch):
    setup(monkeypatch, states={9: READY, 10: READY})
    monkeypatch.setattr(recovery.streaming, "_upsert_mediamtx_path", lambda **_kwargs: pytest.fail("healthy PATCH"))
    monkeypatch.setattr(recovery, "_recreate_path", lambda *_args: pytest.fail("healthy DELETE/ADD"))
    monkeypatch.setattr(recovery, "_add_path", lambda *_args: pytest.fail("healthy ADD"))
    watchdog = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    for _ in range(6):
        assert watchdog.step() == {9: "healthy", 10: "healthy"}
    assert not watchdog.consecutive_failures


def test_only_broken_device_is_recreated(monkeypatch):
    calls = arm_repair(monkeypatch)
    redis_client = FakeRedis()
    watchdog = recovery.StreamRecoveryWatchdog(redis_client, sleep=lambda _: None)
    assert watchdog.step() == {9: "observing", 10: "healthy"}
    assert watchdog.step() == {9: "observing", 10: "healthy"}
    assert watchdog.step() == {9: "recreated-recovered", 10: "healthy"}
    assert calls == [("patch", 9), ("recreate", 9)]
    assert redis_client.get(recovery._keys(9)["backup"])
    assert redis_client.get(recovery._keys(10)["backup"]) is None


def test_other_device_can_repair_in_same_round(monkeypatch):
    calls = arm_repair(monkeypatch, states={9: BROKEN, 10: BROKEN})
    watchdog = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    watchdog.step(); watchdog.step()
    assert watchdog.step() == {9: "recreated-recovered", 10: "recreated-recovered"}
    assert calls == [("patch", 9), ("recreate", 9), ("patch", 10), ("recreate", 10)]


def test_patch_success_skips_delete(monkeypatch):
    calls = arm_repair(monkeypatch, patch_succeeds=True)
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step()[9] == "patch-recovered"
    assert calls == [("patch", 9)]


def test_monitoring_off_disappears_from_targets_and_clears_counter(monkeypatch):
    ids = [(9, "E910006")]
    monkeypatch.setattr(recovery, "_monitored_targets", lambda: ids[:])
    monkeypatch.setattr(recovery, "_path_state", lambda path: BROKEN)
    monkeypatch.setattr(recovery, "_path_config", lambda path: dict(WARM))
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    assert monitor.step() == {9: "observing"}
    ids.clear()
    assert monitor.step() == {}
    assert monitor.consecutive_failures == {}


def test_monitoring_off_during_repair_skips_patch(monkeypatch):
    calls = arm_repair(monkeypatch)
    monkeypatch.setattr(recovery, "_still_monitored", lambda *_: False)
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step()[9] == "monitoring-off"
    assert calls == []


def test_on_demand_and_absent_paths_untouched(monkeypatch):
    setup(monkeypatch, states={9: BROKEN, 10: OFFLINE}, config={9: {"source": "url", "sourceOnDemand": True}})
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    for _ in range(5):
        assert monitor.step() == {9: "not-warm-path", 10: "not-warm-path"}


def test_warm_path_with_no_runtime_is_monitored(monkeypatch):
    setup(monkeypatch, states={9: None, 10: READY})
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    assert monitor.step()[9] == "observing"


def test_transient_failure_resets_counter(monkeypatch):
    state = {9: BROKEN, 10: READY}
    setup(monkeypatch, states=state)
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    monitor.step(); monitor.step()
    state[9] = READY
    assert monitor.step()[9] == "healthy"
    state[9] = BROKEN
    assert monitor.step()[9] == "observing"


def test_one_check_exception_does_not_stop_others(monkeypatch):
    setup(monkeypatch)
    def state(path):
        if path == "cctv-9":
            raise RuntimeError("source url must not leak")
        return READY
    monkeypatch.setattr(recovery, "_path_state", state)
    assert recovery.StreamRecoveryWatchdog(FakeRedis()).step() == {9: "check-error", 10: "healthy"}


def test_cooldown_and_lock_per_camera(monkeypatch):
    calls = arm_repair(monkeypatch, states={9: BROKEN, 10: BROKEN})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["cooldown"], "1", ex=600)
    redis.set(recovery._keys(10)["lock"], "other", ex=180)
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step() == {9: "cooldown", 10: "locked"}
    assert calls == []


def test_hourly_attempt_limit_per_camera(monkeypatch):
    calls = arm_repair(monkeypatch, states={9: BROKEN, 10: BROKEN})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["attempts"], "2", ex=3600)
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step() == {9: "hourly-limit", 10: "recreated-recovered"}
    assert calls == [("patch", 10), ("recreate", 10)]


def test_backup_write_failure_blocks_delete(monkeypatch):
    calls = arm_repair(monkeypatch)
    class BrokenBackupRedis(FakeRedis):
        def set(self, key, value, nx=False, ex=None):
            if key.endswith(":backup"):
                return False
            return super().set(key, value, nx=nx, ex=ex)
    monitor = recovery.StreamRecoveryWatchdog(BrokenBackupRedis(), sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step()[9] == "backup-failed"
    assert calls == [("patch", 9)]


def test_recreate_restores_original_if_add_fails(monkeypatch):
    sent = []
    monkeypatch.setattr(recovery.requests, "delete", lambda *_a, **_k: type("R", (), {"status_code": 200})())
    def fake_post(_url, json, timeout):
        sent.append(json.copy())
        return type("R", (), {"status_code": 500 if len(sent) == 1 else 200})()
    monkeypatch.setattr(recovery.requests, "post", fake_post)
    monkeypatch.setattr(recovery, "_path_config", lambda _path: None)
    original = dict(WARM)
    desired = {**WARM, "source": "https://example.test/new"}
    with pytest.raises(RuntimeError, match="add status=500"):
        recovery._recreate_path("cctv-9", desired, original)
    assert [item["source"] for item in sent] == [desired["source"], original["source"]]


def test_read_failure_never_triggers_recovery(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(recovery, "_path_config", lambda _path: (_ for _ in ()).throw(RuntimeError("unavailable")))
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    for _ in range(4):
        assert monitor.step() == {9: "check-error", 10: "healthy"}
    assert monitor.consecutive_failures == {}


def test_missing_path_requires_recent_warm_proof(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    states, configs = setup(monkeypatch, ids=((9, "E910006"),),
                            states={9: None}, config={})
    calls = []
    monkeypatch.setattr(recovery, "_add_path", lambda *_args: calls.append("add"))
    watchdog = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    for _ in range(4):
        assert watchdog.step() == {9: "not-warm-path"}
    assert not calls


def test_previously_warm_missing_path_adds_without_delete(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    states, configs = setup(monkeypatch, ids=((9, "E910006"),),
                            states={9: READY}, config={9: dict(WARM)})
    redis = FakeRedis()
    watchdog = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    assert watchdog.step() == {9: "healthy"}
    assert redis.get(recovery._keys(9)["warm_seen"]) == "E910006"
    assert redis.expiries[recovery._keys(9)["warm_seen"]] == recovery.WARM_SEEN_TTL_SECONDS
    states[9] = None
    configs.clear()
    calls = []
    def add(path, payload):
        calls.append((path, payload))
        configs[9] = dict(payload)
        states[9] = READY
    monkeypatch.setattr(recovery, "_add_path", add)
    monkeypatch.setattr(recovery, "_recreate_path", lambda *_args: pytest.fail("must not DELETE"))
    assert watchdog.step() == {9: "observing"}
    assert watchdog.step() == {9: "observing"}
    assert watchdog.step() == {9: "missing-path-restored"}
    assert len(calls) == 1
    assert calls[0][0] == "cctv-9"
    assert calls[0][1]["sourceOnDemand"] is False
    assert calls[0][1]["source"] == "https://example.test/old"
    assert watchdog.step() == {9: "healthy"}


def test_missing_path_feature_disabled_keeps_original_behavior(monkeypatch):
    monkeypatch.delenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", raising=False)
    states, configs = setup(monkeypatch, ids=((9, "E910006"),),
                            states={9: READY}, config={9: dict(WARM)})
    monitor = recovery.StreamRecoveryWatchdog(FakeRedis(), sleep=lambda _: None)
    assert monitor.step()[9] == "healthy"
    states[9] = None
    configs.clear()
    monkeypatch.setattr(recovery, "_add_path", lambda *_a: pytest.fail("disabled ADD"))
    for _ in range(5):
        assert monitor.step()[9] == "not-warm-path"


def test_missing_path_proof_bound_to_external_id(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    states, configs = setup(monkeypatch, ids=((9, "E999999"),), states={9: None}, config={})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["warm_seen"], "E910006", ex=600)
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monkeypatch.setattr(recovery, "_add_path", lambda *_a: pytest.fail("different ID ADD"))
    assert monitor.step()[9] == "not-warm-path"


def test_switch_to_on_demand_invalidates_warm_proof(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    states, configs = setup(monkeypatch, ids=((9, "E910006"),),
                            states={9: READY}, config={9: dict(WARM)})
    redis = FakeRedis()
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    assert monitor.step()[9] == "healthy"
    states[9] = BROKEN
    configs[9]["sourceOnDemand"] = True
    assert monitor.step()[9] == "not-warm-path"
    assert redis.get(recovery._keys(9)["warm_seen"]) == "-"
    configs.clear()
    assert monitor.step()[9] == "not-warm-path"


def test_missing_path_off_guard_blocks_add(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    setup(monkeypatch, ids=((9, "E910006"),), states={9: None}, config={})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["warm_seen"], "E910006", ex=600)
    monkeypatch.setattr(recovery, "_still_monitored", lambda *_a: False)
    monkeypatch.setattr(recovery, "_add_path", lambda *_a: pytest.fail("OFF ADD"))
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step()[9] == "monitoring-off"


def test_missing_path_race_new_config_blocks_add(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    states, configs = setup(monkeypatch, ids=((9, "E910006"),),
                            states={9: None}, config={})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["warm_seen"], "E910006", ex=600)
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monitor.step(); monitor.step()
    calls = [0]
    def config_change(_path):
        calls[0] += 1
        # Existing path appears between lock acquisition and final ADD guard.
        return {"sourceOnDemand": True, "source": "https://example.test/new"} if calls[0] >= 3 else None
    monkeypatch.setattr(recovery, "_path_config", config_change)
    monkeypatch.setattr(recovery, "_add_path", lambda *_a: pytest.fail("racing ADD"))
    assert monitor.step()[9] == "config-changed"


def test_missing_path_rate_limit_guard(monkeypatch):
    monkeypatch.setenv("OCTV_CCTV_RECOVERY_RECREATE_MISSING_ENABLED", "1")
    setup(monkeypatch, ids=((9, "E910006"),), states={9: None}, config={})
    redis = FakeRedis()
    redis.set(recovery._keys(9)["warm_seen"], "E910006", ex=600)
    redis.set(recovery._keys(9)["attempts"], "2", ex=3600)
    monkeypatch.setattr(recovery, "_add_path", lambda *_a: pytest.fail("rate-limited ADD"))
    monitor = recovery.StreamRecoveryWatchdog(redis, sleep=lambda _: None)
    monitor.step(); monitor.step()
    assert monitor.step()[9] == "hourly-limit"
