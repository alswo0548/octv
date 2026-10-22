from __future__ import annotations

from backend.app.cctvs import streaming


def test_mediamtx_path_ready_when_stream_is_playable(
    monkeypatch,
):
    monkeypatch.setattr(
        streaming,
        "_get_mediamtx_runtime_path",
        lambda _path_name: {
            "online": True,
            "ready": True,
            "available": True,
            "tracks": ["H264"],
        },
    )

    assert (
        streaming._is_mediamtx_path_ready(
            "cctv-1"
        )
        is True
    )


def test_mediamtx_path_not_ready_when_online_but_stream_unavailable(
    monkeypatch,
):
    """
    KTICT HLS 인증 만료 등으로 MediaMTX source 프로세스는
    online=True 상태로 남아 있어도 실제 영상은 준비되지 않을 수 있다.

    이 상태를 정상 source로 재사용하면 안 된다.
    """
    monkeypatch.setattr(
        streaming,
        "_get_mediamtx_runtime_path",
        lambda _path_name: {
            "online": True,
            "ready": False,
            "available": False,
            "tracks": [],
        },
    )

    assert (
        streaming._is_mediamtx_path_ready(
            "cctv-1"
        )
        is False
    )


def test_prepare_stream_reuses_ready_source(
    monkeypatch,
):
    calls = {
        "resolve": 0,
        "upsert": 0,
    }

    monkeypatch.setattr(
        streaming,
        "_is_mediamtx_path_ready",
        lambda _path_name: True,
    )

    def fake_get_utic_stream_url(
        _external_cctv_id,
    ):
        calls["resolve"] += 1
        return (
            "https://example.test/stream",
            {},
        )

    def fake_upsert_mediamtx_path(
        **_kwargs,
    ):
        calls["upsert"] += 1

    monkeypatch.setattr(
        streaming,
        "get_utic_stream_url",
        fake_get_utic_stream_url,
    )

    monkeypatch.setattr(
        streaming,
        "_upsert_mediamtx_path",
        fake_upsert_mediamtx_path,
    )

    result = streaming.prepare_cctv_stream(
        cctv_id=1,
        external_cctv_id="E910012",
    )

    assert result["cctv_id"] == 1
    assert result["path"] == "cctv-1"

    assert calls["resolve"] == 0
    assert calls["upsert"] == 0


def test_prepare_stream_force_reloads_unready_source(
    monkeypatch,
):
    captured = {}

    monkeypatch.setattr(
        streaming,
        "_is_mediamtx_path_ready",
        lambda _path_name: False,
    )

    monkeypatch.setattr(
        streaming,
        "get_utic_stream_url",
        lambda _external_cctv_id: (
            "https://example.test/source",
            {},
        ),
    )

    monkeypatch.setattr(
        streaming,
        "_build_mediamtx_source",
        lambda stream_url: (
            stream_url,
            "test-fingerprint",
        ),
    )

    def fake_upsert_mediamtx_path(
        **kwargs,
    ):
        captured.update(kwargs)

    monkeypatch.setattr(
        streaming,
        "_upsert_mediamtx_path",
        fake_upsert_mediamtx_path,
    )

    result = streaming.prepare_cctv_stream(
        cctv_id=1,
        external_cctv_id="E910012",
    )

    assert result["cctv_id"] == 1
    assert result["path"] == "cctv-1"

    assert captured == {
        "path_name": "cctv-1",
        "source_url": (
            "https://example.test/source"
        ),
        "source_fingerprint": (
            "test-fingerprint"
        ),
        "keep_warm": True,
        "force_reload": True,
    }