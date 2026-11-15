/* ExpireGuard モック用のバックエンド（素の JS、ブラウザ内だけで動く）。
 * 本物のアプリの API（api / extract / notify の各 Lambda）の代わりに、メモリ上で同じ形の応答を返す。
 * - データはページを読み込み直すと消える（保存しない）
 * - アップロードされたファイルは読まずに捨てる。読み取りは、画像の内容と無関係な固定のサンプルを返す
 * - メールは送らない
 * ブラウザでは window.ExpireGuardMock、Node（テスト）では module.exports として公開する。 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ExpireGuardMock = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var UPLOAD_URL = "https://mock.invalid/upload";
  var MAX_BYTES = 3750000; // 本物の api /uploads と同じ上限
  var RISK_WINDOW_DAYS = 30;
  var MAX_TEST_ITEMS = 5;
  var ALLOWED_TYPES = { "image/png": "png", "image/jpeg": "jpg" };
  var PATCHABLE = ["service", "points", "amount", "expiryDate", "isLimited", "cycle"];

  /* ---------- 日付 ---------- */
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function isoOf(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function startOfDay(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
  function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
  function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0); }
  function parseIso(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    var p = value.split("-");
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    return isoOf(d) === value ? d : null;
  }
  function daysBetween(from, to) { return Math.round((to - from) / 86400000); }

  function positiveInt(value) {
    var n = typeof value === "string" ? parseInt(value.replace(/[^0-9]/g, ""), 10) : value;
    return typeof n === "number" && isFinite(n) && n > 0 && Math.floor(n) === n ? n : null;
  }

  /* ---------- 項目の検証（本物の validate_item_fields と同じ規則） ---------- */
  function validateItem(data) {
    var bad = [];
    var kind = data.kind === undefined ? "points" : data.kind;
    if (kind !== "points" && kind !== "subscription") return { error: { fields: ["kind"] } };
    var service = typeof data.service === "string" ? data.service.trim() : "";
    if (!service || service.length > 80) bad.push("service");
    if (!parseIso(data.expiryDate)) bad.push("expiryDate");
    var item = { kind: kind, service: service, expiryDate: data.expiryDate };
    if (kind === "points") {
      var points = positiveInt(data.points);
      if (points === null) bad.push("points");
      item.points = points;
      item.amount = points;
      item.isLimited = !!data.isLimited;
    } else {
      var amount = positiveInt(data.amount);
      if (amount === null) bad.push("amount");
      if (data.cycle !== "monthly" && data.cycle !== "yearly") bad.push("cycle");
      item.amount = amount;
      item.cycle = data.cycle;
    }
    return bad.length ? { error: { fields: bad } } : { item: item };
  }

  function badRequest(fields) {
    return { status: 400, body: { message: "Invalid input", fields: fields } };
  }

  function createMockBackend(options) {
    var opts = options || {};
    var today = opts.today || function () { return new Date(); };
    var counter = 0;
    var newId = opts.newId || function () { counter += 1; return "mock-" + counter; };
    var items = [];
    var extractCount = 0;

    function find(id) {
      for (var i = 0; i < items.length; i++) { if (items[i].itemId === id) return i; }
      return -1;
    }
    function active() { return items.filter(function (i) { return i.status === "active"; }); }
    function byExpiry(list) {
      return list.slice().sort(function (a, b) {
        return a.expiryDate < b.expiryDate ? -1 : a.expiryDate > b.expiryDate ? 1 : 0;
      });
    }
    function daysLeft(item) { return daysBetween(startOfDay(today()), parseIso(item.expiryDate)); }

    /* 画像の内容とは無関係な、固定のサンプル。実在のサービス名は使わない */
    function sampleDrafts() {
      var base = startOfDay(today());
      var drafts;
      if (extractCount % 2 === 0) {
        drafts = [
          { kind: "points", service: "Sample Points", points: 114, amount: 114, expiryDate: isoOf(addDays(base, 12)), isLimited: true },
          { kind: "points", service: "Sample Points", points: 460, amount: 460, expiryDate: isoOf(addDays(base, 90)), isLimited: true }
        ];
      } else {
        drafts = [
          { kind: "subscription", service: "Sample Streaming", amount: 1490, expiryDate: isoOf(endOfMonth(base)), cycle: "monthly" }
        ];
      }
      extractCount += 1;
      return drafts.map(function (d) {
        var draft = Object.assign({ itemId: newId() }, d, { status: "draft" });
        items.push(draft);
        return draft;
      });
    }

    function buildSummary() {
      var now = startOfDay(today());
      var list = byExpiry(active());
      var risk = list.filter(function (i) {
        var left = daysLeft(i);
        return i.kind === "points" && left >= 0 && left <= RISK_WINDOW_DAYS;
      });
      var charges = list.filter(function (i) {
        var d = parseIso(i.expiryDate);
        return i.kind === "subscription" && d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
      });
      var sum = function (arr) { return arr.reduce(function (s, i) { return s + (i.amount || 0); }, 0); };
      var saved = items.filter(function (i) { return i.status === "used" || i.status === "cancelled"; });
      return {
        atRiskAmount: sum(risk),
        atRiskCount: risk.length,
        upcomingCharges: { amount: sum(charges), count: charges.length },
        savedAmount: sum(saved),
        items: list.map(function (i) { return Object.assign({}, i, { daysLeft: daysLeft(i) }); })
      };
    }

    function createItem(body) {
      var payload = body || {};
      var checked = validateItem(payload);
      if (checked.error) return badRequest(checked.error.fields);
      var now = new Date().toISOString();
      var idx = -1;
      if (payload.draftId !== undefined && payload.draftId !== null) {
        idx = typeof payload.draftId === "string" ? find(payload.draftId) : -1;
        if (idx < 0 || items[idx].status !== "draft") return { status: 404, body: { message: "Draft not found" } };
      }
      var item = Object.assign({}, checked.item, {
        itemId: idx >= 0 ? items[idx].itemId : newId(),
        status: "active",
        createdAt: now,
        updatedAt: now
      });
      if (idx >= 0) { items[idx] = item; } else { items.push(item); }
      return { status: 201, body: item };
    }

    function updateItem(id, body) {
      var payload = body || {};
      var idx = find(id);
      if (idx < 0) return { status: 404, body: { message: "Item not found" } };
      var existing = items[idx];
      if (existing.status !== "active") return { status: 409, body: { message: "Only active items can be updated" } };
      var action = existing.kind === "subscription" ? "cancelled" : "used";
      if (payload.status !== undefined && payload.status !== action) {
        return badRequest(["status"]);
      }
      var merged = Object.assign({}, existing);
      PATCHABLE.forEach(function (k) { if (k in payload) merged[k] = payload[k]; });
      var checked = validateItem(merged);
      if (checked.error) return badRequest(checked.error.fields);
      var updated = Object.assign({}, existing, checked.item, { updatedAt: new Date().toISOString() });
      if (payload.status !== undefined) updated.status = payload.status;
      items[idx] = updated;
      return { status: 200, body: updated };
    }

    function testNotification() {
      var due = byExpiry(active()).slice(0, MAX_TEST_ITEMS);
      var sample = due.length === 0;
      return { status: 200, body: { sent: true, sample: sample, count: sample ? 1 : due.length } };
    }

    function handle(method, path, body) {
      var clean = String(path || "").split("?")[0];
      var m = /^\/items\/([^/]+)$/.exec(clean);
      var id = m ? decodeURIComponent(m[1]) : null;
      var route = method + " " + (m ? "/items/{id}" : clean);

      switch (route) {
        case "POST /uploads": {
          var type = body && body.contentType;
          var ext = typeof type === "string" ? ALLOWED_TYPES[type] : undefined;
          if (!ext) return { status: 400, body: { message: "Please choose a PNG or JPEG image" } };
          return { status: 200, body: { url: UPLOAD_URL, fields: {}, key: "mock/" + newId() + "." + ext, maxBytes: MAX_BYTES } };
        }
        case "POST /extract":
          if (!body || typeof body.key !== "string") return badRequest(["key"]);
          return { status: 200, body: { items: sampleDrafts() } };
        case "GET /items":
          return { status: 200, body: { items: byExpiry(active()) } };
        case "GET /summary":
          return { status: 200, body: buildSummary() };
        case "POST /items":
          return createItem(body);
        case "PATCH /items/{id}":
          return updateItem(id, body);
        case "DELETE /items/{id}": {
          var idx = find(id);
          if (idx < 0) return { status: 404, body: { message: "Item not found" } };
          items.splice(idx, 1);
          return { status: 204, body: null };
        }
        case "POST /notify/test":
          return testNotification();
        default:
          return { status: 404, body: { message: "Not found" } };
      }
    }

    return { handle: handle };
  }

  /* fetch を差し替える。API とアップロード先はモックが応答し、それ以外のURLへは通信しない */
  function installMock(win, options) {
    var apiBase = options.apiBase;
    var backend = options.backend;
    var ResponseCtor = win.Response || Response;

    win.fetch = function (input, init) {
      var url = typeof input === "string" ? input : (input && input.url) || String(input);
      var method = String((init && init.method) || "GET").toUpperCase();

      if (url === UPLOAD_URL) {
        // ファイルは読まずに捨てる（init.body には触れない）
        return Promise.resolve(new ResponseCtor(null, { status: 204 }));
      }
      if (url.indexOf(apiBase) === 0) {
        var body;
        if (init && typeof init.body === "string") {
          try { body = JSON.parse(init.body); } catch (e) { body = undefined; }
        }
        var out = backend.handle(method, url.slice(apiBase.length), body);
        var payload = out.body === null || out.body === undefined ? null : JSON.stringify(out.body);
        return Promise.resolve(new ResponseCtor(payload, {
          status: out.status,
          headers: { "Content-Type": "application/json" }
        }));
      }
      return Promise.reject(new TypeError("blocked by mock: " + url));
    };
  }

  return { createMockBackend: createMockBackend, installMock: installMock, UPLOAD_URL: UPLOAD_URL };
});
