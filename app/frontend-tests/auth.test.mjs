// フロント認証モジュール（frontend/auth.js）のテスト。依存なし: `node --test frontend-tests/`
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const { createAuth, AuthError } = require("../frontend/auth.js");

const CLIENT_ID = "test-client-id";
const REGION = "us-east-1";
const ENDPOINT = `https://cognito-idp.${REGION}.amazonaws.com/`;
const STORAGE_KEY = "expireguard.auth";

/** sessionStorage 相当のメモリ実装 */
function memoryStorage() {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: (k) => data.delete(k),
    _data: data,
  };
}

/** fetch スタブ。応答キューを順に返し、呼び出しを記録する */
function stubFetch(replies) {
  const calls = [];
  const queue = [...replies];
  const fn = async (url, opts) => {
    calls.push({ url, opts, body: JSON.parse(opts.body), target: opts.headers["X-Amz-Target"] });
    const reply = queue.shift();
    if (reply instanceof Error) throw reply;
    const status = reply.status ?? 200;
    return { ok: status >= 200 && status < 300, status, json: async () => reply.body };
  };
  fn.calls = calls;
  return fn;
}

function setup(replies, { now = () => 1_000_000 } = {}) {
  const storage = memoryStorage();
  const fetchFn = stubFetch(replies);
  const auth = createAuth({ clientId: CLIENT_ID, region: REGION, fetchFn, storage, now });
  return { auth, storage, fetchFn };
}

const SUCCESS = {
  body: {
    AuthenticationResult: {
      IdToken: "id-1",
      AccessToken: "access-1",
      RefreshToken: "refresh-1",
      ExpiresIn: 3600,
    },
  },
};

test("signIn は USER_PASSWORD_AUTH で InitiateAuth を呼びトークンを保存する", async () => {
  const { auth, storage, fetchFn } = setup([SUCCESS]);
  const result = await auth.signIn("user@example.com", "Pass-word-123!");
  assert.deepEqual(result, { status: "signed_in" });
  const call = fetchFn.calls[0];
  assert.equal(call.url, ENDPOINT);
  assert.equal(call.opts.method, "POST");
  assert.equal(call.target, "AWSCognitoIdentityProviderService.InitiateAuth");
  assert.equal(call.opts.headers["Content-Type"], "application/x-amz-json-1.1");
  assert.equal(call.body.AuthFlow, "USER_PASSWORD_AUTH");
  assert.equal(call.body.ClientId, CLIENT_ID);
  assert.deepEqual(call.body.AuthParameters, {
    USERNAME: "user@example.com",
    PASSWORD: "Pass-word-123!",
  });
  const saved = JSON.parse(storage.getItem(STORAGE_KEY));
  assert.equal(saved.idToken, "id-1");
  assert.equal(saved.refreshToken, "refresh-1");
  assert.equal(saved.expiresAt, 1_000_000 + 3600 * 1000);
});

test("アクセストークンは保存しない", async () => {
  const { auth, storage } = setup([SUCCESS]);
  await auth.signIn("user@example.com", "x");
  assert.ok(!storage.getItem(STORAGE_KEY).includes("access-1"));
});

test("localStorage ではなく渡された storage にだけ書く", async () => {
  const { auth, storage } = setup([SUCCESS]);
  await auth.signIn("user@example.com", "x");
  assert.deepEqual([...storage._data.keys()], [STORAGE_KEY]);
});

test("誤った資格情報は AuthError(NotAuthorizedException) で未保存", async () => {
  const { auth, storage } = setup([
    { status: 400, body: { __type: "NotAuthorizedException", message: "Incorrect username or password." } },
  ]);
  await assert.rejects(
    () => auth.signIn("user@example.com", "bad"),
    (err) => err instanceof AuthError && err.code === "NotAuthorizedException",
  );
  assert.equal(storage.getItem(STORAGE_KEY), null);
});

test("__type が名前空間付きでも末尾のコードを使う", async () => {
  const { auth } = setup([
    { status: 400, body: { __type: "com.amazonaws#NotAuthorizedException", message: "x" } },
  ]);
  await assert.rejects(
    () => auth.signIn("a@example.com", "b"),
    (err) => err.code === "NotAuthorizedException",
  );
});

test("ネットワーク障害は NetworkError の AuthError にする", async () => {
  const { auth } = setup([new TypeError("Failed to fetch")]);
  await assert.rejects(
    () => auth.signIn("a@example.com", "b"),
    (err) => err instanceof AuthError && err.code === "NetworkError",
  );
});

test("NEW_PASSWORD_REQUIRED チャレンジを返し、トークンは保存しない", async () => {
  const { auth, storage } = setup([
    {
      body: {
        ChallengeName: "NEW_PASSWORD_REQUIRED",
        Session: "session-xyz",
        ChallengeParameters: { USER_ID_FOR_SRP: "uuid-user-1" },
      },
    },
  ]);
  const result = await auth.signIn("user@example.com", "Temp-pass-1!");
  assert.deepEqual(result, {
    status: "new_password_required",
    challenge: { session: "session-xyz", username: "uuid-user-1" },
  });
  assert.equal(storage.getItem(STORAGE_KEY), null);
});

test("未対応のチャレンジは UnsupportedChallenge", async () => {
  const { auth } = setup([{ body: { ChallengeName: "SMS_MFA", Session: "s" } }]);
  await assert.rejects(
    () => auth.signIn("a@example.com", "b"),
    (err) => err.code === "UnsupportedChallenge",
  );
});

test("completeNewPassword は RespondToAuthChallenge を呼びトークンを保存する", async () => {
  const { auth, storage, fetchFn } = setup([SUCCESS]);
  const result = await auth.completeNewPassword(
    { session: "session-xyz", username: "uuid-user-1" },
    "New-pass-word-1!",
  );
  assert.deepEqual(result, { status: "signed_in" });
  const call = fetchFn.calls[0];
  assert.equal(call.target, "AWSCognitoIdentityProviderService.RespondToAuthChallenge");
  assert.deepEqual(call.body, {
    ChallengeName: "NEW_PASSWORD_REQUIRED",
    ClientId: CLIENT_ID,
    Session: "session-xyz",
    ChallengeResponses: { USERNAME: "uuid-user-1", NEW_PASSWORD: "New-pass-word-1!" },
  });
  assert.equal(JSON.parse(storage.getItem(STORAGE_KEY)).idToken, "id-1");
});

test("パスワードポリシー違反は InvalidPasswordException", async () => {
  const { auth } = setup([
    { status: 400, body: { __type: "InvalidPasswordException", message: "policy" } },
  ]);
  await assert.rejects(
    () => auth.completeNewPassword({ session: "s", username: "u" }, "short"),
    (err) => err.code === "InvalidPasswordException",
  );
});

test("getIdToken は有効期限内ならそのまま返し通信しない", async () => {
  const { auth, fetchFn } = setup([SUCCESS]);
  await auth.signIn("a@example.com", "b");
  assert.equal(await auth.getIdToken(), "id-1");
  assert.equal(fetchFn.calls.length, 1);
});

test("保存が無ければ getIdToken は null", async () => {
  const { auth } = setup([]);
  assert.equal(await auth.getIdToken(), null);
  assert.equal(auth.isSignedIn(), false);
});

test("期限切れ間近はリフレッシュトークンで更新し、リフレッシュトークンは維持する", async () => {
  let t = 1_000_000;
  const { auth, storage, fetchFn } = setup(
    [SUCCESS, { body: { AuthenticationResult: { IdToken: "id-2", AccessToken: "a2", ExpiresIn: 3600 } } }],
    { now: () => t },
  );
  await auth.signIn("a@example.com", "b");
  t += 3600 * 1000 - 30 * 1000; // 残り30秒（余裕60秒を切る）
  assert.equal(await auth.getIdToken(), "id-2");
  const call = fetchFn.calls[1];
  assert.equal(call.body.AuthFlow, "REFRESH_TOKEN_AUTH");
  assert.equal(call.body.ClientId, CLIENT_ID);
  assert.deepEqual(call.body.AuthParameters, { REFRESH_TOKEN: "refresh-1" });
  const saved = JSON.parse(storage.getItem(STORAGE_KEY));
  assert.equal(saved.idToken, "id-2");
  assert.equal(saved.refreshToken, "refresh-1");
});

test("同時に呼んでもリフレッシュは1回だけ", async () => {
  let t = 1_000_000;
  const { auth, fetchFn } = setup(
    [SUCCESS, { body: { AuthenticationResult: { IdToken: "id-2", ExpiresIn: 3600 } } }],
    { now: () => t },
  );
  await auth.signIn("a@example.com", "b");
  t += 3600 * 1000;
  const [x, y] = await Promise.all([auth.getIdToken(), auth.getIdToken()]);
  assert.equal(x, "id-2");
  assert.equal(y, "id-2");
  assert.equal(fetchFn.calls.length, 2);
});

test("リフレッシュ失敗（トークン失効）は保存を消して null を返す", async () => {
  let t = 1_000_000;
  const { auth, storage } = setup(
    [SUCCESS, { status: 400, body: { __type: "NotAuthorizedException", message: "Refresh Token has expired" } }],
    { now: () => t },
  );
  await auth.signIn("a@example.com", "b");
  t += 3600 * 1000;
  assert.equal(await auth.getIdToken(), null);
  assert.equal(storage.getItem(STORAGE_KEY), null);
});

test("リフレッシュ時のネットワーク障害では保存を消さずエラーにする", async () => {
  let t = 1_000_000;
  const { auth, storage } = setup([SUCCESS, new TypeError("offline")], { now: () => t });
  await auth.signIn("a@example.com", "b");
  t += 3600 * 1000;
  await assert.rejects(() => auth.getIdToken(), (err) => err.code === "NetworkError");
  assert.notEqual(storage.getItem(STORAGE_KEY), null);
});

test("forceRefresh は期限内でも更新する（401 後の再試行用）", async () => {
  const { auth, fetchFn } = setup([
    SUCCESS,
    { body: { AuthenticationResult: { IdToken: "id-2", ExpiresIn: 3600 } } },
  ]);
  await auth.signIn("a@example.com", "b");
  assert.equal(await auth.getIdToken({ forceRefresh: true }), "id-2");
  assert.equal(fetchFn.calls[1].body.AuthFlow, "REFRESH_TOKEN_AUTH");
});

test("signOut は保存を消す", async () => {
  const { auth, storage } = setup([SUCCESS]);
  await auth.signIn("a@example.com", "b");
  assert.equal(auth.isSignedIn(), true);
  auth.signOut();
  assert.equal(storage.getItem(STORAGE_KEY), null);
  assert.equal(auth.isSignedIn(), false);
});

test("壊れた保存値は未ログイン扱いにして消す", async () => {
  const { auth, storage } = setup([]);
  storage.setItem(STORAGE_KEY, "{not json");
  assert.equal(await auth.getIdToken(), null);
  assert.equal(storage.getItem(STORAGE_KEY), null);
});

test("設定（clientId / region）が無ければ作成時にエラー", () => {
  assert.throws(() => createAuth({ region: REGION, fetchFn() {}, storage: memoryStorage() }));
  assert.throws(() => createAuth({ clientId: "c", fetchFn() {}, storage: memoryStorage() }));
});
