/**
 * 실행: node --test tests/web_delivery.test.mjs (Node 24)
 * 실제 createApi와 전달 연결 코드를 사용하고 HTTP 경계만 모의 처리합니다.
 * 관리자 권한·DB ID·선택 검증·중복 클릭·늦은 세션 응답·Push 상태 의미를 검사합니다.
 * 실제 DB·Firebase·휴대폰 검증이나 실제 발송은 수행하지 않습니다.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { createApi } from "../frontend/web/src/api.ts";
import {
  DeliveryError,
  deliverToAgencies,
  getDeliveryContext,
  loadDeliverySnapshot,
  pushStatusLabels,
  setDeliveryContext,
  subscribeDeliveryContext,
} from "../frontend/web/src/delivery.ts";

const user = { id: 3, role: "CONTROL_ADMIN", is_active: true };
const incident = {
  id: 42,
  incident_no: "SERVER-INCIDENT-42",
  cctv_name: "서버 CCTV",
  hazard_type: "flood",
  status: "CONFIRMED",
};
const candidates = {
  incident_id: 42,
  incident_status: "CONFIRMED",
  items: [
    {
      agency_id: 12,
      agency_name: "서버 소방서",
      agency_type: "FIRE",
      recommendation_rank: 1,
      recommendation_status: "RECOMMENDED",
      routes: [
        {
          id: 101,
          route_name: "실제 경로 A",
          distance_m: 1200,
          duration_sec: 300,
          total_score: 85,
          disqualify_reason: null,
        },
        {
          id: 102,
          route_name: "제외 경로 B",
          distance_m: 800,
          duration_sec: 180,
          total_score: null,
          disqualify_reason: "도로 통제",
        },
      ],
    },
    {
      agency_id: 13,
      agency_name: "서버 도로관리",
      agency_type: "ROAD",
      recommendation_rank: 2,
      recommendation_status: "RECOMMENDED",
      routes: [],
    },
  ],
};
const result = {
  incident_id: 42,
  incident_status: "SENT",
  items: [
    {
      agency_id: 12,
      agency_recommendation_id: 22,
      status: "DELIVERED",
      newly_delivered: true,
      created_notification_count: 2,
    },
  ],
  created_notification_count: 2,
  push_status: "QUEUED",
};

// 늦은 응답을 재현하기 위한 제어 가능한 Promise입니다. 시간에 의존하는 sleep은 쓰지 않습니다.
function deferred() {
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

// 실제 API 요청의 JWT·메서드·본문을 보존하며 네트워크 대신 서버 응답을 제공합니다.
function connect(t, handler) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    const request = { path: new URL(url).pathname, options };
    calls.push(request);
    const custom = await handler?.(request, calls);
    if (custom) return custom;
    if (request.path === "/api/auth/me") return Response.json(user);
    if (request.path === "/api/incidents/42") return Response.json(incident);
    if (request.path.endsWith("/recommendations"))
      return Response.json(candidates);
    if (request.path.endsWith("/deliveries")) return Response.json(result);
    assert.fail("허용하지 않은 API 요청: " + request.path);
  });
  // 세션이 바뀌면 새 API를 만들어 setDeliveryContext를 교체하는 계약입니다.
  const api = createApi("https://api.example.test", () => "test-web-session");
  setDeliveryContext({ user, api, incidentId: 42 });
  return {
    api,
    calls,
    posts: () => calls.filter((call) => call.options.method === "POST"),
  };
}

// 오류 코드로 실패 단계를 검사하여 원문 오류 메시지나 토큰 출력에 의존하지 않습니다.
const hasCode = (code) => (error) =>
  error instanceof DeliveryError && error.code === code;

beforeEach(() => setDeliveryContext(null));
afterEach(() => setDeliveryContext(null));

describe("WEB 실제 기관 전달 연결", { concurrency: false }, () => {
  it("인증·실제 사건 연결이 없으면 조회나 전달 네트워크 요청을 하지 않는다", async (t) => {
    const fetchMock = t.mock.method(globalThis, "fetch", () =>
      assert.fail("네트워크 호출 금지"),
    );
    await assert.rejects(loadDeliverySnapshot(), hasCode("NO_CONTEXT"));
    await assert.rejects(
      deliverToAgencies({}, [{ agency_id: 12 }]),
      hasCode("NO_CONTEXT"),
    );
    assert.equal(fetchMock.mock.callCount(), 0);
  });

  it("mock 문자열·불리언·정밀도 초과 ID와 기관 사용자를 차단하고 이전 연결도 해제한다", (t) => {
    const { api, calls } = connect(t);
    for (const incidentId of [
      "SEL-001",
      "42",
      true,
      0,
      -1,
      1.5,
      Number.MAX_SAFE_INTEGER + 1,
    ]) {
      assert.throws(
        () => setDeliveryContext({ user, api, incidentId }),
        hasCode("INVALID_CONTEXT"),
      );
      assert.equal(getDeliveryContext(), null);
    }
    assert.throws(
      () =>
        setDeliveryContext({
          user: { ...user, role: "RESPONDER" },
          api,
          incidentId: 42,
        }),
      hasCode("FORBIDDEN"),
    );
    assert.throws(
      () =>
        setDeliveryContext({
          user: { ...user, is_active: false },
          api,
          incidentId: 42,
        }),
      hasCode("FORBIDDEN"),
    );
    assert.equal(calls.length, 0);
  });

  it("/auth/me가 403이면 사건·기관 조회를 진행하지 않는다", async (t) => {
    const { calls } = connect(t, () =>
      Response.json({ detail: "forbidden" }, { status: 403 }),
    );
    await assert.rejects(loadDeliverySnapshot(), hasCode("FORBIDDEN"));
    assert.deepEqual(
      calls.map((call) => call.path),
      ["/api/auth/me"],
    );
  });

  it("주입된 사용자와 JWT 본인이 다르면 서버 사건을 표시하지 않는다", async (t) => {
    const { calls } = connect(t, ({ path }) =>
      path === "/api/auth/me" ? Response.json({ ...user, id: 99 }) : undefined,
    );
    await assert.rejects(loadDeliverySnapshot(), hasCode("SESSION_CHANGED"));
    assert.equal(calls.length, 1);
  });

  it("서버에서 역할이 변경되거나 비활성화된 사용자는 조회를 진행하지 않는다", async (t) => {
    let serverUser = { ...user, role: "RESPONDER" };
    const { calls } = connect(t, ({ path }) =>
      path === "/api/auth/me" ? Response.json(serverUser) : undefined,
    );
    await assert.rejects(loadDeliverySnapshot(), hasCode("FORBIDDEN"));
    serverUser = { ...user, is_active: false };
    await assert.rejects(loadDeliverySnapshot(), hasCode("FORBIDDEN"));
    assert.ok(calls.every((call) => call.path === "/api/auth/me"));
  });

  it("실제 사건번호·기관·0개 경로를 그대로 읽고 DB 숫자 ID로 한 번 전달한다", async (t) => {
    const { calls, posts } = connect(t);
    const snapshot = await loadDeliverySnapshot();
    assert.equal(snapshot.incident.incident_no, "SERVER-INCIDENT-42");
    assert.equal(snapshot.candidates[0].agency_name, "서버 소방서");
    assert.deepEqual(snapshot.candidates[1].routes, []);
    const received = await deliverToAgencies(snapshot, [
      { agency_id: 12, route_candidate_id: 101 },
    ]);
    assert.equal(received.incident_status, "SENT");
    assert.equal(posts().length, 1);
    assert.equal(posts()[0].path, "/api/agencies/incidents/42/deliveries");
    assert.deepEqual(JSON.parse(posts()[0].options.body), {
      selections: [{ agency_id: 12, route_candidate_id: 101 }],
    });
    assert.ok(
      calls.every(
        (call) =>
          call.options.headers.get("Authorization") ===
          "Bearer test-web-session",
      ),
    );
    assert.equal(
      calls.filter((call) => call.path === "/api/auth/me").length,
      2,
    );
    assert.ok(
      calls.every(
        (call) =>
          !call.path.endsWith("/sent") && !call.path.endsWith("/confirm"),
      ),
    );
  });

  it("중복·미추천 기관·잘못된 경로·문자 ID·예상 밖 필드는 POST 전에 차단한다", async (t) => {
    const { posts } = connect(t);
    const snapshot = await loadDeliverySnapshot();
    for (const selections of [
      [],
      [{ agency_id: 12 }, { agency_id: 12 }],
      [{ agency_id: 999 }],
      [{ agency_id: "12" }],
      [{ agency_id: 12, route_candidate_id: 102 }],
      [{ agency_id: 13, route_candidate_id: 101 }],
      [{ agency_id: 12, route_candidate_id: "A" }],
      [{ agency_id: 12, user_id: 999 }],
    ]) {
      await assert.rejects(
        deliverToAgencies(snapshot, selections),
        hasCode("INVALID_SELECTION"),
      );
    }
    await assert.rejects(
      deliverToAgencies({ ...snapshot }, [{ agency_id: 12 }]),
      hasCode("STALE_SNAPSHOT"),
    );
    assert.equal(posts().length, 0);
  });

  it("DETECTED 사건은 자동 확인하거나 전달하지 않는다", async (t) => {
    const { calls, posts } = connect(t, ({ path }) => {
      if (path === "/api/incidents/42")
        return Response.json({ ...incident, status: "DETECTED" });
      if (path.endsWith("/recommendations"))
        return Response.json({ ...candidates, incident_status: "DETECTED" });
    });
    const snapshot = await loadDeliverySnapshot();
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("STATE_CHANGED"),
    );
    assert.equal(posts().length, 0);
    assert.ok(calls.every((call) => !call.path.endsWith("/confirm")));
  });

  it("잘못된 사건의 추천 응답을 mock이나 다른 사건으로 대체하지 않는다", async (t) => {
    const { posts } = connect(t, ({ path }) =>
      path.endsWith("/recommendations")
        ? Response.json({ ...candidates, incident_id: 99 })
        : undefined,
    );
    await assert.rejects(loadDeliverySnapshot(), hasCode("INVALID_RESPONSE"));
    assert.equal(posts().length, 0);
  });

  it("Push 큐 확인 실패·꺼짐을 DB 전달 실패로 바꾸지 않는다", async (t) => {
    let pushStatus = "QUEUED";
    connect(t, ({ path }) =>
      path.endsWith("/deliveries")
        ? Response.json({ ...result, push_status: pushStatus })
        : undefined,
    );
    for (pushStatus of [
      "QUEUED",
      "PARTIALLY_QUEUED",
      "QUEUE_UNCONFIRMED",
      "DISABLED",
      "NO_NEW_NOTIFICATIONS",
      "NOT_QUEUED",
    ]) {
      const received = await deliverToAgencies(await loadDeliverySnapshot(), [
        { agency_id: 12 },
      ]);
      assert.equal(received.items[0].newly_delivered, true);
      assert.equal(received.incident_status, "SENT");
      assert.equal(received.push_status, pushStatus);
      assert.doesNotMatch(
        pushStatusLabels[pushStatus],
        /수신 완료|표시 완료|발송 성공/,
      );
    }
  });

  it("전달 직전 다른 요청이 완료한 기관은 서버 COMPLETED 결과를 보존한다", async (t) => {
    connect(t, ({ path }) =>
      path.endsWith("/deliveries")
        ? Response.json({
            ...result,
            items: [
              {
                ...result.items[0],
                status: "COMPLETED",
                newly_delivered: false,
                created_notification_count: 0,
              },
            ],
            created_notification_count: 0,
            push_status: "NO_NEW_NOTIFICATIONS",
          })
        : undefined,
    );
    const received = await deliverToAgencies(await loadDeliverySnapshot(), [
      { agency_id: 12 },
    ]);
    assert.equal(received.items[0].status, "COMPLETED");
    assert.equal(received.items[0].newly_delivered, false);
    assert.equal(received.created_notification_count, 0);
  });

  it("연속 클릭해도 동시에 두 POST를 보내지 않는다", async (t) => {
    const entered = deferred();
    const release = deferred();
    const { posts } = connect(t, async ({ path }) => {
      if (path.endsWith("/deliveries")) {
        entered.resolve();
        await release.promise;
        return Response.json(result);
      }
    });
    const snapshot = await loadDeliverySnapshot();
    const first = deliverToAgencies(snapshot, [{ agency_id: 12 }]);
    await entered.promise;
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("BUSY"),
    );
    release.resolve();
    await first;
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("STALE_SNAPSHOT"),
    );
    assert.equal(posts().length, 1);
  });

  it("POST 통신 실패는 결과 미확인으로 처리하고 같은 조회로 자동·반복 전송하지 않는다", async (t) => {
    const { posts } = connect(t, ({ path }) => {
      if (path.endsWith("/deliveries"))
        throw new TypeError("test network failure");
    });
    const snapshot = await loadDeliverySnapshot();
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("DELIVERY_UNCONFIRMED"),
    );
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("STALE_SNAPSHOT"),
    );
    assert.equal(posts().length, 1);
  });

  it("잘못된 성공 응답도 DB 저장 실패로 단정하거나 자동 재전송하지 않는다", async (t) => {
    const { posts } = connect(t, ({ path }) =>
      path.endsWith("/deliveries")
        ? Response.json({ ...result, incident_id: 99 })
        : undefined,
    );
    const snapshot = await loadDeliverySnapshot();
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("DELIVERY_UNCONFIRMED"),
    );
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("STALE_SNAPSHOT"),
    );
    assert.equal(posts().length, 1);
  });

  it("세션 변경 전 시작한 늦은 조회는 취소 신호를 보내고 결과를 폐기한다", async (t) => {
    const entered = deferred();
    const release = deferred();
    let oldSignal;
    connect(t, async ({ path, options }) => {
      if (path === "/api/incidents/42") {
        oldSignal = options.signal;
        entered.resolve();
        await release.promise; // 서버가 취소 신호를 무시하고 응답하는 상황도 재현합니다.
        return Response.json(incident);
      }
    });
    const pending = loadDeliverySnapshot();
    await entered.promise;
    setDeliveryContext(null);
    assert.equal(oldSignal.aborted, true);
    release.resolve();
    await assert.rejects(pending, hasCode("SESSION_CHANGED"));
  });

  it("전달 직전 본인 확인 중 계정이 바뀌면 POST를 시작하지 않는다", async (t) => {
    const entered = deferred();
    const release = deferred();
    let authCount = 0;
    const { posts } = connect(t, async ({ path }) => {
      if (path === "/api/auth/me" && ++authCount === 2) {
        entered.resolve();
        await release.promise;
        return Response.json(user);
      }
    });
    const snapshot = await loadDeliverySnapshot();
    const pending = deliverToAgencies(snapshot, [{ agency_id: 12 }]);
    await entered.promise;
    setDeliveryContext(null);
    release.resolve();
    await assert.rejects(pending, hasCode("SESSION_CHANGED"));
    assert.equal(posts().length, 0);
  });

  it("로그아웃 뒤 돌아온 POST 성공을 새 사용자 화면에 반환하지 않는다", async (t) => {
    const entered = deferred();
    const release = deferred();
    const { api, posts } = connect(t, async ({ path }) => {
      if (path.endsWith("/deliveries")) {
        entered.resolve();
        await release.promise;
        return Response.json(result);
      }
    });
    const pending = deliverToAgencies(await loadDeliverySnapshot(), [
      { agency_id: 12 },
    ]);
    await entered.promise;
    setDeliveryContext(null);
    setDeliveryContext({ user: { ...user, id: 99 }, api, incidentId: 99 });
    release.resolve();
    await assert.rejects(pending, hasCode("SESSION_CHANGED"));
    assert.equal(posts().length, 1); // 이미 서버로 보낸 POST를 취소했다고 DB rollback으로 해석하지 않습니다.
  });

  it("연결 변경을 구독하고 이전 화면 버전의 조회·선택을 거부한다", async (t) => {
    const { api, calls } = connect(t);
    const oldContext = getDeliveryContext();
    const snapshot = await loadDeliverySnapshot(oldContext.version);
    const seen = [];
    const unsubscribe = subscribeDeliveryContext(() =>
      seen.push(getDeliveryContext()),
    );
    setDeliveryContext(null);
    setDeliveryContext({ user, api, incidentId: 42 });
    unsubscribe();
    const before = calls.length;
    await assert.rejects(
      loadDeliverySnapshot(oldContext.version),
      hasCode("SESSION_CHANGED"),
    );
    await assert.rejects(
      deliverToAgencies(snapshot, [{ agency_id: 12 }]),
      hasCode("STALE_SNAPSHOT"),
    );
    assert.equal(calls.length, before);
    assert.equal(seen[0], null);
    assert.ok(seen[1].version > oldContext.version);
  });
});
