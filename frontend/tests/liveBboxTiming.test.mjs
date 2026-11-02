import assert from 'node:assert/strict';
import { selectLiveFrame as select } from '../web/src/components/liveBboxTiming.ts';
const frame = {t:4, age_sec:.1, width:1920, height:1080, source_epoch:'1', boxes:[]};
assert.equal(select([frame],4.2,.1),frame);
for (const [time,elapsed] of [[3.9,.1],[4.5,.1],[4.2,3],[NaN,.1],[4.2,-1]]) assert.equal(select([frame],time,elapsed),null);
assert.equal(select([{...frame,age_sec:-1}],4.1,0),null);
assert.equal(select([{...frame,width:NaN}],4.1,0),null);
assert.equal(select([frame,{...frame,t:4.1}],4.2,0).t,4.1);
console.log('9 timing assertions passed');
