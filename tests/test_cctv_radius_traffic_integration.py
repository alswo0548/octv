"""반경 수위 + ITS 주변 돌발 + MCP Context 연결: 네트워크/DB 미사용."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ai.runtime_queries import create_query_factory, TRAFFIC_FIELDS
from ai.contracts import ContextSnapshot
from ai.risk_priority.rules import assess, RISK_POLICIES
from backend.app.integrations import auto_match_providers as providers
from backend.app.integrations import cctv_mapping as cm
from backend.app.integrations import water_level, normalization
from tests.test_cctv_auto_mapping_cache import FakeRedis


class RadiusWaterTrafficTests(unittest.TestCase):
    def setUp(self):
        self.cctv = {"id":3,"cctv_id":3,"latitude":37.1824818,"longitude":127.0958378,
                     "name":"동탄터널","cctv_name":"동탄터널","region_code":"41597",
                     "provider":"UTIC","address":"화성시"}
        self.now = datetime(2026, 10, 22, 5, 40, tzinfo=timezone.utc)
        self.cache = FakeRedis()
        redis_patcher = patch.object(cm, '_redis', return_value=self.cache)
        redis_patcher.start()
        self.addCleanup(redis_patcher.stop)

    def station(self, code, name, lat, caution=None, warning=None, danger=None):
        return {"wlobscd":code, "obsnm":name, "lat":lat,
                "lon":self.cctv["longitude"],
                "wrnwl":caution,"almwl":warning,"srswl":danger}

    def test_radius_uses_official_threshold_station_not_closest_without_limits(self):
        stations = [self.station('1101641','느티교',37.2013),
                    self.station('1101645','탑동대교',37.2395,8.5,10.5,13.3)]
        chosen = providers.choose_water_station(self.cctv, stations)
        self.assertEqual(chosen['status'], 'NEARBY_STATION_WITH_THRESHOLDS')
        self.assertEqual(chosen['station_id'], '1101645')
        self.assertGreater(chosen['distance_m'], 6000)
        self.assertEqual(chosen['radius_m'], 10000)
        self.assertFalse(chosen['flood_impact_verified'])
        self.assertEqual(chosen['candidates'][0]['station_id'], '1101641')

    def test_radius_limit_and_no_threshold_fallback(self):
        stations = [self.station('1101641','느티교',37.2013),
                    self.station('1101645','탑동대교',37.2395,8.5,10.5,13.3)]
        close = providers.choose_water_station(self.cctv, stations, radius_m=3000)
        self.assertEqual(close['status'], 'NEARBY_STATION_NO_THRESHOLDS')
        self.assertEqual(close['station_id'], '1101641')
        out = providers.choose_water_station(self.cctv, stations, radius_m=1000)
        self.assertEqual(out['status'], 'NO_STATION_WITHIN_RADIUS')

    def test_preparation_wires_nearby_station_to_existing_official_water_request(self):
        water_result = providers.choose_water_station(self.cctv, [
            self.station('1101641','느티교',37.2013),
            self.station('1101645','탑동대교',37.2395,8.5,10.5,13.3)])
        env = {"OCTV_AUTO_MAPPING_ENABLED":"1", "WATER_LEVEL_API_KEY":"SECRET_W",
               "TRAFFIC_API_KEY":"SECRET_T", "WEATHER_API_KEY":"SECRET_K"}
        with patch.dict('os.environ', env), \
             patch.object(providers, 'find_water_mapping', return_value=water_result) as find_water, \
             patch.object(providers, 'find_traffic_mapping', return_value={
                 'status':'LINK_GEOMETRY_UNAVAILABLE','candidates': []}):
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), 'CREATED')
            factory = create_query_factory({'cctvs': {}}, env)
            query = factory(self.cctv, self.now)
            refs = cm.mapping_reference_for(self.cctv)
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), 'CACHED')
        find_water.assert_called_once()
        self.assertTrue(query['water_level']['mapped'])
        self.assertEqual(query['water_level']['spec']['station_id'], '1101645')
        self.assertEqual(refs['water_station_mapping']['status'], 'NEARBY_STATION_SELECTED')
        self.assertEqual(refs['water_station_mapping']['radius_m'], 10000)
        self.assertTrue(refs['water_station_mapping']['official_thresholds_available'])
        self.assertFalse(refs['water_station_mapping']['flood_impact_verified'])
        self.assertTrue(query['traffic_nearby_events']['mapped'])
        self.assertEqual(query['traffic_nearby_events']['radius_m'], 1000)
        self.assertTrue(all(not v.get('mapped') for v in query['traffic'].values()
                            if isinstance(v,dict)))
        stored = json.dumps(self.cache.values)
        self.assertNotIn('SECRET_', stored)

    def test_water_observation_and_threshold_still_use_existing_parser(self):
        q = {"mapped":True, "source":"HRFCO_WATERLEVEL_10M", "now":self.now,
             "url":"https://redacted.test", "params":{}, "max_age_sec":1800,
             "spec":{"rows_path":["content"],"station_key":"wlobscd",
                     "station_id":"1101645","value_key":"wl","time_key":"ymdhm",
                     "time_format":"%Y%m%d%H%M","timezone":timezone(timedelta(hours=9)),
                     "scale":1}, "station_info":{"url":"https://redacted.test/info","params":{}}}
        observations = {"content":[{"wlobscd":"1101645","wl":"9.0","ymdhm":"202610221430"}]}
        official = {"content":[{"wlobscd":"1101645", "wrnwl":8.5,
                                "almwl":10.5, "srswl":13.3}]}
        with patch.object(normalization, 'get_json', return_value=observations), \
             patch.object(water_level, 'get_json', return_value=official):
            metric = water_level.fetch_data(q)
            risk = water_level.classify_risk_level(q, metric)
        self.assertEqual(metric['status'], 'OK')
        self.assertEqual(metric['value'], 9.0)
        self.assertEqual(risk['value'], 'CAUTION')
        self.assertEqual(risk['status'], 'OK')

    def test_water_stale_rejected_without_score(self):
        q = {"mapped":True, "source":"HRFCO_WATERLEVEL_10M", "now":self.now,
             "url":"https://redacted.test", "params":{}, "max_age_sec":1800,
             "spec":{"rows_path":["content"],"station_key":"wlobscd",
                     "station_id":"1101645","value_key":"wl","time_key":"ymdhm",
                     "time_format":"%Y%m%d%H%M","timezone":timezone(timedelta(hours=9)),
                     "scale":1}}
        with patch.object(normalization, 'get_json', return_value={"content":[
            {"wlobscd":"1101645", "wl":"9.0","ymdhm":"202610221200"}]}):
            metric = water_level.fetch_data(q)
        risk = water_level.classify_risk_level(q, metric)
        self.assertEqual(metric['status'], 'STALE')
        self.assertEqual(risk['status'], 'STALE')
        self.assertIsNone(risk['value'])

    def test_radius_changes_invalidate_mapping_without_delete(self):
        with patch.dict('os.environ', {'OCTV_WATER_STATION_RADIUS_M':'10000'}):
            self.assertEqual(cm.prepare_cached_mapping(self.cctv), 'CREATED')
            self.assertIsNotNone(cm.get_cached_mapping(self.cctv))
        with patch.dict('os.environ', {'OCTV_WATER_STATION_RADIUS_M':'3000'}):
            self.assertIsNone(cm.get_cached_mapping(self.cctv))
        self.assertIn('octv:context:mapping:v6:3',self.cache.values)

    def test_traffic_event_nearby_filtered_by_distance_and_date_and_cached(self):
        now = self.now
        response = {"response":{"resultCode":"0","data":[
            {"eventId":"E1","eventType":"accident","coordx":"127.0958378",
             "coordy":"37.1860","startDate":"20261022140000",
             "roadName":"인근도로","linkId":"123456"},
            {"eventId":"E2","coordx":"127.0958378","coordy":"37.21"},
            {"eventId":"E3","coordx":"127.0958378","coordy":"37.1860",
             "endDate":"20261022120000"},
            {"eventId":"E4","coordx":"bad","coordy":"37.1860"}
        ]}}
        with patch.object(providers,'_safe_get_json',return_value=response) as fetch:
            result = providers.find_nearby_traffic_events(self.cctv,'SECRET',
                self.cache, now=now)
            again = providers.find_nearby_traffic_events(self.cctv,'SECRET',
                self.cache, now=now+timedelta(seconds=30))
        self.assertEqual(result['status'],'NEARBY_EVENTS_FOUND')
        self.assertEqual(result['nearby_total'],1)
        self.assertEqual(result['events'][0]['event_id'],'E1')
        self.assertEqual(result,again)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0],providers.ITS_EVENT_URL)
        self.assertEqual(fetch.call_args.kwargs if fetch.call_args.kwargs else {}, {})
        self.assertNotIn('SECRET',json.dumps(self.cache.values))

    def test_traffic_event_missing_geometry_not_fake_no_events(self):
        with patch.object(providers, '_safe_get_json',return_value={
            'response':{'resultCode':'0','data':[{'eventId':'E1'}]}}):
            record=providers.find_nearby_traffic_events(self.cctv,'KEY',self.cache,now=self.now)
        self.assertEqual(record['status'],'EVENT_COORDINATES_UNAVAILABLE')
        self.assertEqual(record['events'],[])
        self.assertFalse(any('nearby_events:' in k for k in self.cache.values))

    def test_traffic_provider_error_not_zero_events(self):
        with patch.object(providers,'_safe_get_json',return_value={'response':{
            'resultCode':'1','data':[]}}):
            record=providers.find_nearby_traffic_events(self.cctv,'KEY',now=self.now)
        self.assertEqual(record['status'],'API_UNAVAILABLE_OR_UNKNOWN_SCHEMA')

    def test_traffic_event_measurement_not_used_for_rule_score(self):
        query={**self.cctv,"mapped":True,"api_key":"SECRET","radius_m":1000,"now":self.now}
        with patch.object(providers,'_safe_get_json',return_value={
            'response':{'resultCode':'0','data':[{'eventId':'E1',
                'coordx':self.cctv['longitude'],'coordy':self.cctv['latitude']}]}}):
            metric=providers.nearby_event_measurement(query)
        self.assertEqual(metric['status'],'REFERENCE_ONLY')
        self.assertEqual(metric['value'],1)
        self.assertFalse(metric['road_match_verified'])
        context=ContextSnapshot(1,self.now,{},())
        without=assess(context,RISK_POLICIES['flood'])
        context.measurements['traffic_nearby_events']=metric
        with_events=assess(context,RISK_POLICIES['flood'])
        self.assertEqual(without['risk_score'],with_events['risk_score'])

    def test_collect_context_contains_event_reference_without_changing_rule(self):
        # 실행 환경에 DB 드라이버가 없는 경우에도 실제 DB를 건드리지 않고 수집 흐름 검증.
        import importlib.util
        import importlib
        import sys
        from types import ModuleType
        if importlib.util.find_spec('psycopg') is None:
            fake_db = ModuleType('backend.app.db.session')
            fake_db.get_connection = lambda: None
            fake_repo = ModuleType('backend.app.incidents.repository')
            fake_repo.find_detail = lambda *_: None
            with patch.dict(sys.modules, {
                'backend.app.db.session': fake_db,
                'backend.app.incidents.repository': fake_repo,
            }):
                ctx = importlib.import_module('backend.app.integrations.context')
        else:
            ctx = importlib.import_module('backend.app.integrations.context')
        incident = {**self.cctv, 'id': 17, 'cctv_id': 3}
        class Connection:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
        def metric(source='OTHER'):
            return {'value':None,'observed_at':None,'source':source,
                    'unit':'category','status':'NO_MAPPING'}
        evt = {'value':2,'observed_at':self.now.isoformat(),'source':'ITS_NEARBY_TRAFFIC_EVENTS',
               'unit':'events','status':'REFERENCE_ONLY','road_match_verified':False,
               'nearby_events':[{'event_id':'E1','distance_m':200}]}
        queries = {'weather': {'mapped':False},'water_level':{'mapped':False},
                   'traffic':{},'places':{'mapped':False},
                   'traffic_nearby_events':{'mapped':True,'api_key':'SECRET',
                                            'latitude':incident['latitude'],
                                            'longitude':incident['longitude'],
                                            'now':self.now},
                   'mapping_references': {'water_station_mapping':metric('HRFCO')}}
        with patch.object(ctx,'get_connection', return_value=Connection()), \
             patch.object(ctx,'find_detail', return_value=incident), \
             patch.object(ctx.weather,'fetch_observations', return_value={'rainfall_mm': metric()}), \
             patch.object(ctx.water_level,'fetch_data', return_value=metric()), \
             patch.object(ctx.water_level,'classify_risk_level',return_value=metric()), \
             patch.object(ctx.traffic,'fetch_rule_data',return_value={'traffic_control':metric()}), \
             patch.object(ctx.places,'fetch_data',return_value={'nearby_hospital_distance_m':metric()}), \
             patch.object(ctx,'nearby_event_measurement',return_value=evt) as fetch:
            context=ctx.collect_context(17,lambda _incident,_now:queries)
        self.assertEqual(context.incident_id,17)
        self.assertEqual(context.measurements['traffic_nearby_events'],evt)
        self.assertEqual(context.measurements['water_station_mapping']['source'],'HRFCO')
        self.assertIn('ITS_NEARBY_TRAFFIC_EVENTS',context.sources)
        fetch.assert_called_once()

    def test_traffic_event_disabled_without_key(self):
        factory=create_query_factory({'cctvs':{}},{'OCTV_AUTO_MAPPING_ENABLED':'1'})
        self.assertFalse(factory(self.cctv,self.now)['traffic_nearby_events']['mapped'])
        empty=providers.nearby_event_measurement({'mapped':False})
        self.assertEqual(empty['status'],'NO_MAPPING')


if __name__ == '__main__':
    unittest.main()
