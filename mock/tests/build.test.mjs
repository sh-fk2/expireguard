// ビルド（build.mjs）の出力のテスト。依存なし: `node --test mock/tests/*.test.mjs`
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { build } from "../build.mjs";

const out = mkdtempSync(join(tmpdir(), "eg-mock-"));
build(out);
const read = (name) => readFileSync(join(out, name), "utf-8");

// 本物の環境の値は、公開するモックに入れない。値そのものをこのファイルに書くと、テストが値を公開してしまうので、
// 次の3つで検査する。
//  1. 形で見つける: どの環境にも当てはまる文字列、12桁の数字（アカウントID）、メールアドレス
//  2. 手元の app/frontend/config.js（.gitignore 対象）にある API・クライアントの ID
//  3. 環境変数 EXPIREGUARD_REAL_VALUES（カンマ区切り）。アカウントID、メールのドメインなど、手元だけで持つ値
const GENERIC_VALUES = ["amplifyapp.com", "execute-api", "cloudfront.net"];
const GENERIC_PATTERNS = [/\b\d{12}\b/, /[\w.+-]+@[\w-]+(\.[\w-]+)+/];

function localConfigValues() {
  try {
    const config = readFileSync(new URL("../../app/frontend/config.js", import.meta.url), "utf-8");
    const api = config.match(/apiBaseUrl:\s*"(https:\/\/[^"]+)"/);
    const client = config.match(/userPoolClientId:\s*"([^"]+)"/);
    return [api && new URL(api[1]).hostname.split(".")[0], client?.[1]].filter(Boolean);
  } catch {
    return [];
  }
}

const REAL_VALUES = [
  ...GENERIC_VALUES,
  ...localConfigValues(),
  ...(process.env.EXPIREGUARD_REAL_VALUES ?? "").split(",").map((v) => v.trim()).filter(Boolean),
];

test("出力は、必要な5ファイルだけ", () => {
  assert.deepEqual(readdirSync(out).sort(), ["app.js", "auth.js", "config.js", "index.html", "mock-backend.js"]);
});

test("本物の環境の値（API・ユーザープール・メール・アカウントID）が1つも入っていない", () => {
  for (const name of readdirSync(out)) {
    const text = read(name);
    for (const value of REAL_VALUES) assert.ok(!text.includes(value), `${name} に ${value} が含まれている`);
    for (const pattern of GENERIC_PATTERNS) assert.ok(!pattern.test(text), `${name} に ${pattern} に当たる文字列が含まれている`);
  }
});

test("設定は、通信できないダミーのAPIとクライアントIDになっている", () => {
  const config = read("config.js");
  assert.match(config, /https:\/\/mock\.invalid\/api/);
  assert.match(config, /userPoolClientId: "mock"/);
});

test("index.html に、CSP・モックのスクリプト・デモ表示が入り、読み込み順が正しい", () => {
  const html = read("index.html");
  assert.match(html, /Content-Security-Policy/);
  assert.match(html, /connect-src 'self' https:\/\/mock\.invalid/);
  const order = ["config.js", "mock-backend.js", "auth.js", "app.js"].map((f) => html.indexOf(`<script src="${f}">`));
  assert.ok(order.every((i) => i >= 0), "スクリプトが足りない");
  assert.deepEqual([...order].sort((a, b) => a - b), order, "読み込み順が違う");
  assert.match(html, /Demo mode/);
  assert.match(html, /#logout-btn\s*\{\s*display:\s*none/);
});

test("テスト通知の文言が、メールを送らないデモ向けに差し替わっている", () => {
  const app = read("app.js");
  assert.ok(!app.includes('ok_test_sent: "Test notification sent."'));
  assert.ok(!app.includes('ok_test_sent: "テスト通知を送信しました。"'));
  assert.match(app, /no email is sent/);
  assert.match(app, /メールは送信されません/);
});

test("app.js は、文言の差し替え以外は本物と同じ", () => {
  const real = readFileSync(new URL("../../app/frontend/app.js", import.meta.url), "utf-8");
  const mock = read("app.js");
  const realLines = real.split("\n");
  const mockLines = mock.split("\n");
  assert.equal(mockLines.length, realLines.length);
  const changed = realLines.filter((line, i) => line !== mockLines[i]);
  assert.ok(changed.length <= 4, `変更された行が多すぎる: ${changed.length}`);
});
