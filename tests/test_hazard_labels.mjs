/** 실행: node --test tests/test_hazard_labels.mjs · 웹과 모바일 상세의 공통 표시명 검증. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { hazardLabel, hazardLabels } from "../shared/src/hazards.ts";

test("네 서비스 유형만 등록하고 심각 도로 파손을 별도 유형으로 표시한다", () => {
  const expected = {
    flood: "도로 침수",
    fallen_tree: "쓰러진 나무",
    severe_road_damage: "심각한 도로 파손",
    road_obstacle: "도로 장애물",
  };
  assert.deepEqual(Object.keys(hazardLabels).sort(), Object.keys(expected).sort());
  for (const [type, label] of Object.entries(expected)) {
    assert.equal(hazardLabel(type), label);
  }
});

test("미지원 값은 현재 유형으로 바꾸지 않는다", () => {
  assert.equal(hazardLabel("unrecognized_type"), "unrecognized_type · 과거/미확인 유형");
});
