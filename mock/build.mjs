// モックの公開用ファイル一式（site/）を組み立てる。実行: `node mock/build.mjs`
// 本物のフロント（app/frontend）の index.html と app.js を土台にし、次の差分だけを加える。
//  - config.js / auth.js / mock-backend.js: ダミーの設定、ログインの代用、メモリ上のバックエンド
//  - index.html: CSP（外部への通信を制限）、デモ表示、ログアウトボタンの非表示、スクリプトの追加
//  - app.js: テスト通知の完了メッセージ4行だけを「メールは送らない」デモ向けの文言に差し替え
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, "..", "app", "frontend");
const MOCK_API = "https://mock.invalid/api";

const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data: blob:",
  `connect-src 'self' ${new URL(MOCK_API).origin}`,
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const BANNER_CSS = `
      .mock-banner { background: #fff7e0; color: #5c4400; border-bottom: 1px solid #f0d98a; padding: 8px 16px; font-size: 13px; text-align: center; }
      #logout-btn { display: none !important; }
    `;
const BANNER_HTML =
  '\n    <div class="mock-banner" role="note">Demo mode: nothing is saved or sent. Uploaded files are discarded, and your data disappears when you reload the page.</div>';

// app.js の差し替え（文字列が見つからなければ、本物の側が変わったとみなして失敗させる）
const MESSAGE_PATCHES = [
  ['ok_test_sent: "Test notification sent."',
    'ok_test_sent: "Demo mode: no email is sent. In the real app, a test email arrives here."'],
  ['ok_test_sample: "No active items yet, so a sample notification was sent."',
    'ok_test_sample: "Demo mode: no email is sent. In the real app, a sample email arrives here."'],
  ['ok_test_sent: "テスト通知を送信しました。"',
    'ok_test_sent: "デモ版のため、メールは送信されません。実際のアプリでは、ここで通知メールが届きます。"'],
  ['ok_test_sample: "有効なアイテムがないため、サンプルの通知を送信しました。"',
    'ok_test_sample: "デモ版のため、メールは送信されません。実際のアプリでは、ここでサンプルのメールが届きます。"'],
];

function replaceOnce(text, from, to) {
  if (!text.includes(from)) throw new Error(`差し替え対象が見つかりません: ${from.slice(0, 60)}`);
  return text.replace(from, () => to);
}

export function build(outDir = join(here, "site")) {
  mkdirSync(outDir, { recursive: true });

  let html = readFileSync(join(frontend, "index.html"), "utf-8");
  html = replaceOnce(html, '<meta charset="utf-8" />',
    `<meta charset="utf-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`);
  html = replaceOnce(html, "</style>", `${BANNER_CSS}</style>`);
  html = replaceOnce(html, "<body>", `<body>${BANNER_HTML}`);
  html = replaceOnce(html, '<script src="auth.js"></script>',
    '<script src="mock-backend.js"></script>\n    <script src="auth.js"></script>');
  writeFileSync(join(outDir, "index.html"), html);

  let app = readFileSync(join(frontend, "app.js"), "utf-8");
  for (const [from, to] of MESSAGE_PATCHES) app = replaceOnce(app, from, to);
  writeFileSync(join(outDir, "app.js"), app);

  writeFileSync(join(outDir, "config.js"),
    `window.EXPIREGUARD_CONFIG = {\n  apiBaseUrl: "${MOCK_API}",\n  userPoolClientId: "mock",\n  region: "us-east-1"\n};\n`);
  copyFileSync(join(here, "src", "auth-stub.js"), join(outDir, "auth.js"));
  copyFileSync(join(here, "src", "mock-backend.js"), join(outDir, "mock-backend.js"));
  return outDir;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.log(`built: ${build()}`);
}
