// 실행: node --test tests/test_api_client.mjs (프로젝트 기준 Node 24)
// 실제 HTTP 통신만 대체하고 WEB·MOBILE의 공통 API 함수를 검사합니다.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

const user = {
  id: 3,
  email: "staff@example.com",
  name: "기관 담당자",
  role: "AGENCY_STAFF",
  agency_id: 7,
  is_active: true,
  notification_enabled: true,
};

for (const platform of ["web", "mobile"]) {
  const { ApiError, createApi, getCurrentUser } = await import(
    `../frontend/${platform}/src/api.ts`
  );

  describe(`${platform} 공통 API`, () => {
    it("요청마다 최신 토큰을 읽고 로그아웃 후에는 인증 헤더를 보내지 않는다", async (t) => {
      const requests = [];
      t.mock.method(globalThis, "fetch", async (url, options) => {
        requests.push({ url, options });
        return Response.json({ items: [] });
      });
      let token = "test-token-1";
      const api = createApi("https://api.example.test/", () => token);

      assert.deepEqual(await api("/api/incidents?page=2"), { items: [] });
      token = "test-token-2";
      await api("/api/incidents");
      token = null;
      await api("/api/agencies");

      assert.equal(
        requests[0].url,
        "https://api.example.test/api/incidents?page=2",
      );
      assert.deepEqual(
        requests.map(({ options }) => options.headers.get("Authorization")),
        ["Bearer test-token-1", "Bearer test-token-2", null],
      );
      assert.equal(requests[0].options.headers.has("Content-Type"), false);
    });

    it("JSON 요청의 본문·메서드·기존 헤더·취소 신호를 유지한다", async (t) => {
      const headers = new Headers({ "X-Request-Id": "example" });
      const controller = new AbortController();
      const body = JSON.stringify({ email: user.email, password: "test-only" });
      t.mock.method(globalThis, "fetch", async (_url, options) => {
        assert.equal(options.method, "POST");
        assert.equal(options.body, body);
        assert.equal(options.signal, controller.signal);
        assert.equal(options.headers.get("X-Request-Id"), "example");
        assert.equal(options.headers.get("Content-Type"), "application/json");
        return Response.json({ user });
      });

      const api = createApi("https://api.example.test", () => null);
      assert.deepEqual(
        await api("/api/auth/login", {
          method: "POST",
          body,
          headers,
          signal: controller.signal,
        }),
        { user },
      );
      assert.equal(headers.has("Content-Type"), false);
    });

    it("폼 본문과 명시한 Content-Type을 JSON으로 덮어쓰지 않는다", async (t) => {
      const requests = [];
      t.mock.method(globalThis, "fetch", async (_url, options) => {
        requests.push(options);
        return Response.json({ ok: true });
      });
      const api = createApi("https://api.example.test", () => null);
      const form = new FormData();
      form.set("name", "example");
      const encoded = new URLSearchParams({ username: user.email });

      await api("/api/example", { method: "POST", body: form });
      await api("/api/auth/token", { method: "POST", body: encoded });
      await api("/api/example", {
        method: "POST",
        body: "plain text",
        headers: { "Content-Type": "text/plain" },
      });

      assert.equal(requests[0].body, form);
      assert.equal(requests[0].headers.has("Content-Type"), false);
      assert.equal(requests[1].body, encoded);
      assert.equal(requests[1].headers.has("Content-Type"), false);
      assert.equal(requests[2].headers.get("Content-Type"), "text/plain");
    });

    it("401·403·404 상태와 서버의 오류 설명을 화면에 전달한다", async (t) => {
      let status = 401;
      t.mock.method(globalThis, "fetch", async () =>
        Response.json({ detail: "접근할 수 없습니다." }, { status }),
      );
      const api = createApi("https://api.example.test", () => null);

      for (status of [401, 403, 404]) {
        await assert.rejects(api("/api/incidents/1"), (error) => {
          assert.ok(error instanceof ApiError);
          assert.equal(error.status, status);
          assert.equal(error.message, "접근할 수 없습니다.");
          return true;
        });
      }
    });

    it("422 검증 오류의 상세 내용을 보존한다", async (t) => {
      const detail = [{ loc: ["body", "email"], msg: "이메일 형식 오류" }];
      t.mock.method(globalThis, "fetch", async () =>
        Response.json({ detail }, { status: 422 }),
      );
      const api = createApi("https://api.example.test", () => null);

      await assert.rejects(api("/api/auth/signup"), (error) => {
        assert.equal(error.status, 422);
        assert.deepEqual(error.detail, detail);
        assert.equal(error.message, "요청을 처리하지 못했습니다.");
        return true;
      });
    });

    it("JSON이 아닌 오류 응답에도 HTTP 상태를 보존한다", async (t) => {
      t.mock.method(
        globalThis,
        "fetch",
        async () => new Response("Unavailable", { status: 503 }),
      );
      const api = createApi("https://api.example.test", () => null);
      await assert.rejects(api("/api/agencies"), (error) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.status, 503);
        return true;
      });
    });

    it("204 응답은 JSON 파싱 없이 처리한다", async (t) => {
      t.mock.method(
        globalThis,
        "fetch",
        async () => new Response(null, { status: 204 }),
      );
      const api = createApi("https://api.example.test", () => null);
      assert.equal(await api("/api/example"), undefined);
    });

    it("통신 실패는 호출한 화면에 그대로 전달한다", async (t) => {
      const failure = new TypeError("Network unavailable");
      t.mock.method(globalThis, "fetch", async () => {
        throw failure;
      });
      const api = createApi("https://api.example.test", () => null);
      await assert.rejects(api("/api/agencies"), (error) => error === failure);
    });

    it("본인 정보의 기관 ID에 맞는 기관명을 조합한다", async (t) => {
      const requests = [];
      t.mock.method(globalThis, "fetch", async (url) => {
        requests.push(url);
        return Response.json(
          url.endsWith("/auth/me")
            ? user
            : [
                { id: 8, name: "다른 기관", agency_type: "FIRE" },
                { id: 7, name: "소속 기관", agency_type: "FIRE" },
              ],
        );
      });
      const api = createApi("https://api.example.test", () => "test-token");
      assert.deepEqual(await getCurrentUser(api), {
        ...user,
        agency_name: "소속 기관",
      });
      assert.deepEqual(requests, [
        "https://api.example.test/api/auth/me",
        "https://api.example.test/api/agencies",
      ]);
    });

    it("소속이 없는 사용자는 기관 목록을 요청하지 않는다", async (t) => {
      const fetchMock = t.mock.method(globalThis, "fetch", async () =>
        Response.json({ ...user, agency_id: null }),
      );
      const api = createApi("https://api.example.test", () => "test-token");
      assert.deepEqual(await getCurrentUser(api), {
        ...user,
        agency_id: null,
        agency_name: null,
      });
      assert.equal(fetchMock.mock.callCount(), 1);
    });

    it("목록에 소속기관이 없으면 다른 기관명으로 대체하지 않는다", async (t) => {
      t.mock.method(globalThis, "fetch", async (url) =>
        Response.json(
          url.endsWith("/auth/me")
            ? user
            : [{ id: 8, name: "다른 기관", agency_type: "FIRE" }],
        ),
      );
      const api = createApi("https://api.example.test", () => "test-token");
      assert.equal((await getCurrentUser(api)).agency_name, null);
    });

    it("본인 인증이 실패하면 기관 조회를 이어서 실행하지 않는다", async (t) => {
      const fetchMock = t.mock.method(globalThis, "fetch", async () =>
        Response.json({ detail: "인증이 필요합니다." }, { status: 401 }),
      );
      const api = createApi("https://api.example.test", () => null);
      await assert.rejects(
        getCurrentUser(api),
        (error) => error.status === 401,
      );
      assert.equal(fetchMock.mock.callCount(), 1);
    });
  });
}
