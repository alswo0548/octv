import assert from 'node:assert/strict';
import { grayscale, moveBox, reconcileVisualTrack } from '../web/src/components/liveBboxTracking.ts';

const W = 80, H = 60;
function shot(time, x, loop = 0) {
  const pixels = new Uint8Array(W * H).fill(25);
  for (let dy = 0; dy < 18; dy++) for (let dx = 0; dx < 22; dx++) {
    pixels[(20 + dy) * W + (x + dx)] = ((dx * 17 + dy * 31) % 160) + 70;
  }
  return {time, loop, width: W, height: H, pixels};
}
const start = shot(20, 20);
const shifted = shot(20.125, 21);
assert.deepEqual(moveBox(start, shifted, [20, 20, 42, 38]), [21, 20, 43, 38]);
const blank = { ...start, pixels: new Uint8Array(W * H).fill(40) };
assert.equal(moveBox(blank, blank, [20, 20, 42, 38]), null);
assert.equal(moveBox(start, { ...shifted, loop: 1 }, [20, 20, 42, 38]), null);
assert.deepEqual([...grayscale(new Uint8ClampedArray([255, 0, 0, 255, 0, 255, 0, 255]))], [76, 149]);

const frames = Array.from({length: 25}, (_, i) => shot(20 + i * 0.125, 20 + Math.floor(i / 2)));
const anchor = {t: 20, age_sec: 0.2, width: W, height: H, source_epoch: 'a', boxes: [
  {bbox: [20, 20, 42, 38], confidence: 0.9, hazard_type: 'flood'}
]};
const out = reconcileVisualTrack(anchor, frames, 23, 0.3);
assert.ok(out);
assert.equal(out.kind, 'visual-track');
assert.ok(out.boxes[0].bbox[0] >= 30);
assert.equal(reconcileVisualTrack(anchor, frames, 23, 4), null);
assert.equal(reconcileVisualTrack(anchor, frames, 24, 0.1), null);
assert.equal(reconcileVisualTrack(anchor, frames.slice(1), 23, 0.1), null);
assert.equal(reconcileVisualTrack(anchor, frames.map(f=>({...f,loop:1})), 23, 0.1)?.kind, 'visual-track');
assert.equal(reconcileVisualTrack(anchor, frames.map((f,i)=>({...f,loop:i<10?0:1})), 23, 0.1), null);
assert.equal(reconcileVisualTrack({...anchor,boxes:[]}, frames, 23, 0.1), null);
console.log('liveBBoxTracking: 13 assertions passed');
