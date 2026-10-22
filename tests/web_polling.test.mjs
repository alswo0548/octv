import assert from "node:assert/strict";
import { test } from "node:test";
import { pollWhileVisible } from "../frontend/web/src/polling.ts";

class Visibility extends EventTarget {
  hidden = false;
  change(hidden) {
    this.hidden = hidden;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}
const flush = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};
const setup = (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  return new Visibility();
};

test("slow requests never overlap; next read waits until completion", async (t) => {
  const visibility = setup(t);
  let finish,
    calls = 0;
  const values = [];
  const stop = pollWhileVisible(
    () => {
      calls++;
      return new Promise((r) => {
        finish = r;
      });
    },
    { visibility, onValue: (v) => values.push(v), onError: assert.fail },
  );
  t.after(stop);
  t.mock.timers.tick(30_000);
  await flush();
  assert.equal(calls, 1);
  finish("stored-result");
  await flush();
  t.mock.timers.tick(9_999);
  assert.equal(calls, 1);
  t.mock.timers.tick(1);
  assert.equal(calls, 2);
  assert.deepEqual(values, ["stored-result"]);
});

test("hidden tab pauses and return triggers immediate read", async (t) => {
  const visibility = setup(t);
  visibility.hidden = true;
  let calls = 0;
  const stop = pollWhileVisible(async () => ++calls, {
    visibility,
    onValue() {},
    onError: assert.fail,
  });
  t.after(stop);
  assert.equal(calls, 0);
  visibility.change(false);
  await flush();
  assert.equal(calls, 1);
  visibility.change(true);
  t.mock.timers.tick(30_000);
  await flush();
  assert.equal(calls, 1);
  visibility.change(false);
  await flush();
  assert.equal(calls, 2);
});

test("unmount/session change aborts and discards a late response", async (t) => {
  const visibility = setup(t);
  let signal,
    finish,
    settled = 0;
  const stop = pollWhileVisible(
    (s) => {
      signal = s;
      return new Promise((r) => {
        finish = r;
      });
    },
    {
      visibility,
      onValue: assert.fail,
      onError: assert.fail,
      onSettled: () => settled++,
    },
  );
  stop();
  assert.equal(signal.aborted, true);
  finish("old-account");
  await flush();
  t.mock.timers.tick(30_000);
  assert.equal(settled, 0);
});

test("transient failure stays an error and next success can recover", async (t) => {
  const visibility = setup(t);
  let calls = 0;
  const seen = [];
  const stop = pollWhileVisible(
    async () => {
      if (++calls === 1) throw new Error("offline");
      return 0;
    },
    {
      visibility,
      onValue: (value) => seen.push(value),
      onError: () => seen.push("error"),
    },
  );
  t.after(stop);
  await flush();
  assert.deepEqual(seen, ["error"]);
  t.mock.timers.tick(10_000);
  await flush();
  assert.deepEqual(seen, ["error", 0]);
});

test("401 and 403 stop periodic retries even after tab return", async (t) => {
  const visibility = setup(t);
  for (const status of [401, 403]) {
    let calls = 0;
    const stop = pollWhileVisible(
      async () => {
        calls++;
        throw { status };
      },
      { visibility, onValue: assert.fail, onError() {} },
    );
    await flush();
    t.mock.timers.tick(30_000);
    visibility.change(false);
    await flush();
    assert.equal(calls, 1);
    stop();
  }
});

test("opt-out retains single read even in a hidden tab", async (t) => {
  const visibility = setup(t);
  visibility.hidden = true;
  let calls = 0;
  const stop = pollWhileVisible(async () => ++calls, {
    visibility,
    intervalMs: 0,
    onValue() {},
    onError: assert.fail,
  });
  t.after(stop);
  await flush();
  t.mock.timers.tick(30_000);
  visibility.change(false);
  assert.equal(calls, 1);
});
