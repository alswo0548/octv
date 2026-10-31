import assert from 'node:assert/strict';
import { test } from 'node:test';
import { incidentLabel, contextStatus } from '../frontend/web/src/incidentLabel.ts';
import { mappingStatus } from '../frontend/web/src/externalDisplay.ts';
import { makeMapViewport } from '../frontend/web/src/mapViewport.ts';
import { hideIncident, hiddenIncidentIds, restoreHiddenIncidents } from '../frontend/web/src/incidentVisibility.ts';
test('display identifier changes priority but retains exact server ID', () => {
 const i = {id: 12, priority:'P2',hazard_type:'fallen_tree'};
 assert.equal(incidentLabel(i),'OCTV_P2_12_tree');
 assert.equal(incidentLabel({...i,priority:'P1'}),'OCTV_P1_12_tree');
 assert.equal(i.id,12);
});
test('missing or stale external data is never zero/normal', () => {
 assert.equal(contextStatus('STALE'),'관측값 유효시간 경과');
 assert.equal(contextStatus('NO_DATA'),'데이터 미수집');
 assert.match(contextStatus('unknown'), /미수집/);
});
test('pan projects real coordinates and requests new tiles', () => {
 const lines=[{id:1,coords:[[127,37.5],[127.01,37.51]]}];
 const a=makeMapViewport(lines,null,820,430);
 const b=makeMapViewport(lines,null,820,430,{zoomDelta:0,dx:300,dy:0});
 const p=a.paths[0].points.split(' ')[0].split(',').map(Number);
 const q=b.paths[0].points.split(' ')[0].split(',').map(Number);
 assert.equal(Math.round(q[0]-p[0]),300);
 assert.notDeepEqual(a.tiles.map(t=>t.key),b.tiles.map(t=>t.key));
 assert.deepEqual(makeMapViewport(lines,null,820,430),a);
});
test('hidden records cannot cross login sessions and can be restored',()=>{
 hideIncident(1,7); assert.ok(hiddenIncidentIds(1).has(7));
 assert.equal(hiddenIncidentIds(2).size,0);
 hideIncident(2,8); restoreHiddenIncidents(2); assert.equal(hiddenIncidentIds(2).size,0);
});

test('demo-only mapping is visibly labelled as simulated', () => {
 assert.match(mappingStatus('DEMO_SIMULATION'), /DEMO 데이터/);
 assert.match(mappingStatus('VERIFIED_EXACT_COLOCATION'), /공식 관측소/);
 assert.match(mappingStatus('CACHE_NOT_READY'), /캐시 없음/);
});


// Numeric provenance regressions: zero, unavailable, and scenario values must differ.
import { externalMetric, externalMetricText } from '../frontend/web/src/externalDisplay.ts';
test('actual zero takes precedence over a demo example and keeps its unit', () => {
 const actual = externalMetric({status:'OK', value:0}, 'mm', 30);
 assert.deepEqual(actual, {text:'0',unit:'mm',simulated:false,numeric:true});
 assert.equal(externalMetricText({status:'OK',value:'0'}, 'm'), '0 m');
});
test('missing, stale and malformed values never gain physical units or become zero', () => {
 for (const value of [null, undefined, '', ' ', true, false, NaN, Infinity, 'Infinity', 'missing', -1, '0x10']) {
   const display = externalMetric({status:'OK',value}, 'm');
   assert.equal(display.unit, '');
   assert.equal(display.numeric, false);
   assert.notEqual(display.text, '0');
 }
 for (const status of ['NO_DATA','NO_MAPPING','STALE','ERROR','TIMEOUT']) {
   assert.equal(externalMetric({status,value:2.4}, 'm').unit, '');
 }
});
test('only a supplied finite scenario example gets a star and unit', () => {
 assert.deepEqual(externalMetric({status:'NO_DATA'}, 'm', 2.4),
   {text:'2.4*',unit:'m',simulated:true,numeric:true});
 assert.equal(externalMetric({status:'NO_MAPPING'}, '', 0).text, '0*');
 assert.equal(externalMetric({status:'NO_DATA'}, 'm', NaN).unit, '');
 assert.equal(externalMetric({status:'OK',value:1.1}, 'm', 2.4).text, '1.1');
});
