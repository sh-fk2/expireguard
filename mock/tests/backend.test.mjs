// モックのバックエンド（src/mock-backend.js）のテスト。依存なし: `node --test mock/tests/`
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const { createMockBackend, installMock, UPLOAD_URL } = require("../src/mock-backend.js");

const TODAY = new Date(2026, 10, 15); // 2026-11-15（ローカル日付）

function iso(days) {
  const d = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate() + days);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function newBackend() {
  let n = 0;
  return createMockBackend({ today: () => TODAY, newId: () => `id-${++n}` });
}

/** アップロード → 読み取り → 登録までを1回行い、登録した項目の一覧を返す */
function importOnce(backend) {
  const up = backend.handle("POST", "/uploads", { contentType: "image/png" });
  const ex = backend.handle("POST", "/extract", { key: up.body.key });
  const saved = ex.body.items.map((d) => {
    const fields = d.kind === "subscription"
      ? { kind: d.kind, service: d.service, amount: d.amount, expiryDate: d.expiryDate, cycle: d.cycle }
      : { kind: d.kind, service: d.service, points: d.points, expiryDate: d.expiryDate, isLimited: d.isLimited };
    return backend.handle("POST", "/items", { ...fields, draftId: d.itemId });
  });
  return { ex, saved };
}

test("画像のアップロード要求には、ダミーのURLとキーを返す", () => {
  const res = newBackend().handle("POST", "/uploads", { contentType: "image/png" });
  assert.equal(res.status, 200);
  assert.equal(res.body.url, UPLOAD_URL);
  assert.equal(typeof res.body.key, "string");
  assert.deepEqual(res.body.fields, {});
  assert.ok(res.body.maxBytes > 0);
});

test("画像以外のアップロード要求は400にする", () => {
  const res = newBackend().handle("POST", "/uploads", { contentType: "text/plain" });
  assert.equal(res.status, 400);
});

test("1回目の読み取りは、期間限定ポイント2件のサンプルを返す", () => {
  const { ex } = importOnce(newBackend());
  assert.equal(ex.status, 200);
  assert.equal(ex.body.items.length, 2);
  for (const item of ex.body.items) {
    assert.equal(item.kind, "points");
    assert.equal(item.isLimited, true);
    assert.equal(item.status, "draft");
  }
  assert.equal(ex.body.items[0].points, 114);
  assert.equal(ex.body.items[0].expiryDate, iso(12));
  assert.equal(ex.body.items[1].points, 460);
});

test("2回目の読み取りは、サブスク1件のサンプルを返し、3回目はポイントに戻る", () => {
  const backend = newBackend();
  importOnce(backend);
  const second = importOnce(backend).ex.body.items;
  assert.equal(second.length, 1);
  assert.equal(second[0].kind, "subscription");
  assert.equal(second[0].cycle, "monthly");
  const third = importOnce(backend).ex.body.items;
  assert.equal(third.length, 2);
  assert.equal(third[0].kind, "points");
});

test("特定のサービス名（実在のブランド）をサンプルに使わない", () => {
  const backend = newBackend();
  const names = [];
  for (let i = 0; i < 4; i++) {
    importOnce(backend).ex.body.items.forEach((d) => names.push(d.service));
  }
  assert.ok(names.every((n) => n.startsWith("Sample ")), names.join(", "));
});

test("最初は空の集計を返す", () => {
  const res = newBackend().handle("GET", "/summary");
  assert.equal(res.status, 200);
  assert.deepEqual(res.body, {
    atRiskAmount: 0,
    atRiskCount: 0,
    upcomingCharges: { amount: 0, count: 0 },
    savedAmount: 0,
    items: [],
  });
});

test("登録すると、30日以内に切れる金額と期限順の一覧に反映される", () => {
  const backend = newBackend();
  importOnce(backend);
  const res = backend.handle("GET", "/summary");
  assert.equal(res.body.atRiskAmount, 114); // 460pt は期限が90日後なので含めない
  assert.equal(res.body.atRiskCount, 1);
  assert.deepEqual(res.body.items.map((i) => i.points), [114, 460]);
  assert.equal(res.body.items[0].daysLeft, 12);
  assert.ok(res.body.items.every((i) => i.status === "active"));
});

test("サブスクを登録すると、今月の自動課金に反映される", () => {
  const backend = newBackend();
  importOnce(backend);
  importOnce(backend); // サブスク
  const res = backend.handle("GET", "/summary");
  assert.equal(res.body.upcomingCharges.count, 1);
  assert.ok(res.body.upcomingCharges.amount > 0);
});

test("存在しない下書きでの登録は404", () => {
  const res = newBackend().handle("POST", "/items", {
    kind: "points", service: "Sample Points", points: 10, expiryDate: iso(5), draftId: "nothing",
  });
  assert.equal(res.status, 404);
});

test("必須項目が足りない登録は400で、項目名を返す", () => {
  const res = newBackend().handle("POST", "/items", { kind: "points", service: "", points: 0, expiryDate: "x" });
  assert.equal(res.status, 400);
  assert.deepEqual(res.body.fields.sort(), ["expiryDate", "points", "service"]);
});

test("下書きなしの手入力でも登録できる", () => {
  const backend = newBackend();
  const res = backend.handle("POST", "/items", {
    kind: "points", service: "Sample Points", points: 300, expiryDate: iso(20), isLimited: false,
  });
  assert.equal(res.status, 201);
  assert.equal(backend.handle("GET", "/summary").body.atRiskAmount, 300);
});

test("「使った」にすると一覧から消え、守れた金額に加算される", () => {
  const backend = newBackend();
  const { saved } = importOnce(backend);
  const id = saved[0].body.itemId;
  const res = backend.handle("PATCH", `/items/${id}`, { status: "used" });
  assert.equal(res.status, 200);
  const summary = backend.handle("GET", "/summary").body;
  assert.equal(summary.savedAmount, 114);
  assert.equal(summary.items.length, 1);
});

test("存在しないアイテムの更新は404、使用済みの更新は409", () => {
  const backend = newBackend();
  assert.equal(backend.handle("PATCH", "/items/none", { status: "used" }).status, 404);
  const { saved } = importOnce(backend);
  const id = saved[0].body.itemId;
  backend.handle("PATCH", `/items/${id}`, { status: "used" });
  assert.equal(backend.handle("PATCH", `/items/${id}`, { status: "used" }).status, 409);
});

test("削除すると一覧から消え、同じものをもう一度削除すると404", () => {
  const backend = newBackend();
  const { saved } = importOnce(backend);
  const id = saved[0].body.itemId;
  assert.equal(backend.handle("DELETE", `/items/${id}`).status, 204);
  assert.equal(backend.handle("GET", "/summary").body.items.length, 1);
  assert.equal(backend.handle("DELETE", `/items/${id}`).status, 404);
});

test("テスト通知は、メールを送らずに結果だけを返す", () => {
  const backend = newBackend();
  const empty = backend.handle("POST", "/notify/test");
  assert.equal(empty.status, 200);
  assert.deepEqual(empty.body, { sent: true, sample: true, count: 1 });
  importOnce(backend);
  const filled = backend.handle("POST", "/notify/test").body;
  assert.equal(filled.sample, false);
  assert.equal(filled.count, 2);
});

test("知らないルートは404", () => {
  assert.equal(newBackend().handle("GET", "/nothing").status, 404);
});

test("インスタンスごとに状態が独立している（リロードで消える）", () => {
  const a = newBackend();
  importOnce(a);
  const b = newBackend();
  assert.equal(b.handle("GET", "/summary").body.items.length, 0);
});

// ---------- fetch の差し替え ----------

const API_BASE = "https://mock.invalid/api";

function fakeWindow() {
  const passed = [];
  return {
    passed,
    fetch: (url) => { passed.push(String(url)); return Promise.resolve(new Response("real")); },
  };
}

test("APIのURLへのfetchは、モックの応答を返し、実際の通信をしない", async () => {
  const win = fakeWindow();
  installMock(win, { apiBase: API_BASE, backend: newBackend() });
  const res = await win.fetch(`${API_BASE}/summary`, { method: "GET", headers: { Authorization: "Bearer x" } });
  assert.equal(res.status, 200);
  assert.equal((await res.json()).atRiskCount, 0);
  assert.deepEqual(win.passed, []);
});

test("アップロード先へのPOSTは、ファイルを読まずに捨てて204を返す", async () => {
  const win = fakeWindow();
  installMock(win, { apiBase: API_BASE, backend: newBackend() });
  let touched = false;
  const body = new Proxy({}, { get() { touched = true; return undefined; } });
  const res = await win.fetch(UPLOAD_URL, { method: "POST", body });
  assert.equal(res.status, 204);
  assert.equal(touched, false);
  assert.deepEqual(win.passed, []);
});

test("モックに関係のないURLへのfetchは、通信せずに拒否する", async () => {
  const win = fakeWindow();
  installMock(win, { apiBase: API_BASE, backend: newBackend() });
  await assert.rejects(() => win.fetch("https://example.com/"), /blocked/);
  assert.deepEqual(win.passed, []);
});

test("APIのリクエスト本文（JSON）をバックエンドに渡す", async () => {
  const win = fakeWindow();
  installMock(win, { apiBase: API_BASE, backend: newBackend() });
  const res = await win.fetch(`${API_BASE}/uploads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contentType: "image/jpeg" }),
  });
  assert.equal(res.status, 200);
  assert.equal((await res.json()).url, UPLOAD_URL);
});
