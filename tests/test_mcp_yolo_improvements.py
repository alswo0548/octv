import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from ai.contracts import Frame, Detection
from ai.demo_v5.timeline import TimelineSource, TimelineFrame, attach_timeline
from ai.demo_v5.live_metadata import metadata, recent_frames
from ai.runtime_queries import create_query_factory
from backend.app.integrations import cctv_mapping as cm, weather, verified_traffic as vt

NOW = datetime(2026, 11, 2, 0, 20, tzinfo=timezone.utc)
CAM = {'id': 3, 'cctv_id': 3, 'latitude': 37.1, 'longitude': 127.1,
       'provider': 'UTIC', 'name': 'camera'}
ENV = {'OCTV_VERIFIED_TRAFFIC_ENABLED': '1', 'TRAFFIC_API_KEY': 'test'}
REVIEW = {**CAM, 'camera_name': 'camera', 'link_id': '1234567890',
          'road_direction_verified': True, 'reviewed_at': '2026-11-01T00:00:00+00:00',
          'reviewed_by': 'operator', 'evidence': 'field inspection', 'direction': 'northbound'}


def test_review_fail_closed():
    assert vt.reviewed_query(CAM, REVIEW, NOW, {})['mapped'] is False
    for field in REVIEW:
        bad = dict(REVIEW); bad.pop(field)
        if field not in ('id', 'name'):
            assert not vt.reviewed_query(CAM, bad, NOW, ENV)['mapped'], field
    for override in ({'latitude': 38}, {'latitude': float('nan')}, {'provider': 'DEMO'},
                     {'camera_name': 'moved'}, {'road_direction_verified': 'true'},
                     {'reviewed_at': '2027-01-01T00:00:00+00:00'}):
        assert not vt.reviewed_query(CAM, {**REVIEW, **override}, NOW, ENV)['mapped']


def test_reviewed_speed_exact_link_and_stale():
    query = vt.reviewed_query(CAM, REVIEW, NOW, ENV)
    assert query['mapped']
    row = {'linkId': REVIEW['link_id'], 'speed': 32, 'createdDate': '20261102091900'}
    with patch.object(cm, '_redis', side_effect=OSError), patch.object(vt, '_safe_get_json', return_value={'data': [row]}):
        result = vt.fetch_speed(query)
        assert result['status'] == 'OK' and result['value'] == 32
        assert result['rule_eligible'] is False
        assert vt.fetch_speed({**query, 'now': NOW + timedelta(minutes=20)})['status'] == 'STALE'
    for rows, status in (([], 'NO_DATA'), ([row, row], 'INVALID'),
                         ([{**row, 'linkId': '99999'}], 'NO_DATA'),
                         ([{**row, 'speed': 'NaN'}], 'INVALID')):
        with patch.object(cm, '_redis', side_effect=OSError), patch.object(vt, '_safe_get_json', return_value={'data': rows}):
            assert vt.fetch_speed(query)['status'] == status


def test_repair_opt_in_and_query_reference_only():
    env = {**ENV, 'OCTV_AUTO_MAPPING_ENABLED': '1', 'OCTV_MAPPING_REPAIR_ON_MISS': '1'}
    with patch.object(cm, 'ensure_mapping', return_value='CREATED') as repair, patch.object(cm, '_redis', side_effect=OSError):
        q = create_query_factory({'cctvs': {'3': {'traffic_link_review': REVIEW}}}, env)(CAM, NOW)
        repair.assert_called_once()
        assert q['traffic_link_observation']['mapped']
        assert all(not v['mapped'] for k, v in q['traffic'].items() if k != 'now')
    with patch.object(cm, 'ensure_mapping') as repair, patch.object(cm, '_redis', side_effect=OSError):
        create_query_factory({}, {'OCTV_AUTO_MAPPING_ENABLED': '1'})(CAM, NOW)
        repair.assert_not_called()


def test_ensure_mapping_handles_identity_and_bad_coordinates():
    with patch.object(cm, 'prepare_cached_mapping', return_value='CREATED') as prepare:
        assert cm.ensure_mapping(CAM) == 'CREATED'
        assert prepare.call_args.args[0]['id'] == 3
    assert cm.ensure_mapping({'cctv_id': 3}) == 'INVALID_COORDINATES'


def test_weather_no_data_previous_hour_only():
    q = create_query_factory({}, {'OCTV_AUTO_MAPPING_ENABLED': '1', 'WEATHER_API_KEY': 'test', 'OCTV_WEATHER_PREVIOUS_HOUR_ENABLED': '1'})(CAM, NOW)['weather']
    good = {'response': {'header': {'resultCode': '00'}, 'body': {'items': {'item': [
        {'category': cat, 'baseDate': '20261102', 'baseTime': '0800', 'obsrValue': '2'}
        for cat in ('RN1', 'WSD')]}}}}
    with patch.object(cm, 'get_cached_weather_payload', return_value=None), patch.object(cm, 'cache_weather_payload'), patch.object(weather, 'get_json', side_effect=[{'response': {'header': {'resultCode': '03'}}}, good]) as get:
        result = weather.fetch_observations(q)
        assert result['rainfall_mm']['status'] == 'OK'
        assert get.call_args_list[1].args[1]['base_time'] == '0800'
    with patch.object(cm, 'get_cached_weather_payload', return_value=None), patch.object(cm, 'cache_weather_payload'), patch.object(weather, 'get_json', return_value={'response': {'header': {'resultCode': '30'}}}) as get:
        assert weather.fetch_observations(q)['rainfall_mm']['status'] == 'ERROR'
        assert get.call_count == 1


def test_timeline_exact_frame_and_reconnect():
    frame = Frame(3, NOW, np.zeros((20, 30, 3), dtype=np.uint8))
    source = SimpleNamespace(read=lambda: frame, open=lambda: None,
                             stream_url='/tmp/N001_demo.mp4', cap=SimpleNamespace(get=lambda _: 1250))
    adapter = TimelineSource(source); adapter.open()
    timed = adapter.read()
    assert timed.image is frame.image and timed.media_time_sec == 1.25
    assert adapter.read() is frame  # repeated/unsupported PTS must not fabricate time
    adapter.open()
    assert adapter.read().source_epoch != timed.source_epoch
    source.cap.get = lambda _: float('nan')
    assert adapter.read() is frame


def test_metadata_exact_detection_and_expiry():
    frame = TimelineFrame(3, NOW, np.zeros((20, 30, 3), dtype=np.uint8), 1.25, 'epoch', 'N001_demo.mp4')
    row = metadata(frame, [Detection('flood', .9, (1, 2, 10, 15), 'actual')])
    assert row['boxes'][0]['bbox'] == [1, 2, 10, 15]
    assert 'image' not in row
    assert recent_frames(json.dumps([row]), NOW, 'N001_demo.mp4', NOW)
    assert not recent_frames(json.dumps([row]), NOW, 'N002_demo.mp4', NOW)
    assert not recent_frames(json.dumps([row]), NOW, 'N001_demo.mp4', NOW + timedelta(seconds=4))
    assert not recent_frames(json.dumps([row]), NOW + timedelta(seconds=1), 'N001_demo.mp4', NOW)
    assert not recent_frames('bad json', NOW, 'N001_demo.mp4', NOW)
    assert not metadata(Frame(3, NOW, frame.image), [])


def test_adapter_only_demo_keeps_worker():
    workers = []
    def factory(camera):
        worker = SimpleNamespace(source=object())
        workers.append(worker)
        return worker
    manager = SimpleNamespace(_worker_factory=factory)
    attach_timeline(SimpleNamespace(_capture_manager=manager))
    demo = manager._worker_factory({'provider': 'DEMO'})
    live = manager._worker_factory({'provider': 'UTIC'})
    assert demo is workers[0] and isinstance(demo.source, TimelineSource)
    assert live is workers[1] and not isinstance(live.source, TimelineSource)


def test_real_opencv_mp4_pts(tmp_path):
    import cv2
    from ai.detection.video import VideoSource
    path = str(tmp_path / 'pts_fixture.mp4')
    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), 25, (64, 48))
    assert out.isOpened()
    for i in range(10):
        out.write(np.full((48, 64, 3), i * 20, np.uint8))
    out.release()
    source = TimelineSource(VideoSource(1, path))
    source.open()
    try:
        pts = [source.read().media_time_sec for _ in range(10)]
        assert all(abs(t - i / 25) < .001 for i, t in enumerate(pts))
    finally:
        source.close()


def test_weather_fallback_disabled_by_default():
    q = create_query_factory({}, {'OCTV_AUTO_MAPPING_ENABLED': '1', 'WEATHER_API_KEY': 'test'})(CAM, NOW)['weather']
    with patch.object(cm, 'get_cached_weather_payload', return_value=None), patch.object(cm, 'cache_weather_payload'), patch.object(weather, 'get_json', return_value={'response': {'header': {'resultCode': '03'}}}) as get:
        weather.fetch_observations(q)
        assert get.call_count == 1


def test_midnight_fallback_preserves_stale_checks():
    q = {'mapped': True, 'url': cm.KMA_WEATHER_URL, 'params': {'base_date': '20261102', 'base_time': '0000'},
         'previous_hour_fallback': True, 'now': NOW, 'max_age_sec': 7200}
    with patch.object(cm, 'get_cached_weather_payload', return_value=None), patch.object(cm, 'cache_weather_payload'), patch.object(weather, 'get_json', return_value={'response': {'header': {'resultCode': '03'}}}) as get:
        assert weather.fetch_observations(q)['rainfall_mm']['status'] == 'ERROR'
        assert get.call_count == 2
        assert get.call_args.args[1]['base_date'] == '20261101'
        assert get.call_args.args[1]['base_time'] == '2300'


def test_metadata_full_queue_drops_without_affecting_detector():
    from queue import Queue
    from ai.demo_v5.live_metadata import MetadataPublisher
    from ai.demo_v5.telemetry import observing_detector
    frame = TimelineFrame(3, NOW, np.zeros((20, 30, 3), dtype=np.uint8), 1, 'a', 'N001_demo.mp4')
    publisher = object.__new__(MetadataPublisher)
    publisher.queue = Queue(maxsize=1)
    publisher.queue.put(('already', {}))
    publisher.submit(frame, [])
    assert publisher.queue.qsize() == 1
    detections = [Detection('flood', .9, (1, 2, 10, 15), 'actual')]
    with patch('ai.demo_v5.live_metadata.enabled', return_value=True), patch('ai.demo_v5.live_metadata.MetadataPublisher', return_value=publisher):
        assert observing_detector(lambda f: detections)(frame) is detections
