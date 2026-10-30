import test from 'node:test';
import assert from 'node:assert/strict';
import { canOpenKakaoNavi } from '../frontend/mobile/src/kakaoNaviEligibility.ts';

const verified = { disqualify_reason: null, verification_status: 'VERIFIED' };
const review = { disqualify_reason: null, verification_status: 'NEEDS_REVIEW' };

test('Kakao Navi can launch to valid destination without OCTV route geometry', () => {
  // SDK receives only destination. GeoJSON path and server navigation_available
  // are intentionally not part of the eligibility contract.
  assert.equal(canOpenKakaoNavi(verified, true), true);
  assert.equal(canOpenKakaoNavi(review, true), true);
});

test('excluded, unknown, missing routes or invalid destinations stay blocked', () => {
  assert.equal(canOpenKakaoNavi(verified, false), false);
  assert.equal(canOpenKakaoNavi(null, true), false);
  assert.equal(canOpenKakaoNavi({ disqualify_reason: 'closed', verification_status: 'VERIFIED' }, true), false);
  assert.equal(canOpenKakaoNavi({ disqualify_reason: null, verification_status: 'DISQUALIFIED' }, true), false);
  assert.equal(canOpenKakaoNavi({ disqualify_reason: null, verification_status: null }, true), false);
});
