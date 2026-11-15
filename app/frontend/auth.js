/* ExpireGuard 認証モジュール（素の JS、SDK なし）。
 * Cognito の InitiateAuth / RespondToAuthChallenge を fetch で直接呼ぶ。
 * トークンは sessionStorage（呼び出し側から注入）に保存し、IdToken のみ API に送る。
 * ブラウザでは window.ExpireGuardAuth、Node（テスト）では module.exports として公開する。 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.ExpireGuardAuth = api;
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var STORAGE_KEY = "expireguard.auth";
  var TARGET_PREFIX = "AWSCognitoIdentityProviderService.";
  var EXPIRY_MARGIN_MS = 60 * 1000; // 期限の60秒前から更新する

  function AuthError(code, message) {
    this.name = "AuthError";
    this.code = code;
    this.message = message || code;
    this.stack = new Error(this.message).stack;
  }
  AuthError.prototype = Object.create(Error.prototype);
  AuthError.prototype.constructor = AuthError;
  function makeAuthError(code, message) { return new AuthError(code, message); }

  function createAuth(options) {
    var clientId = options && options.clientId;
    var region = options && options.region;
    var fetchFn = options && options.fetchFn;
    var storage = options && options.storage;
    var now = (options && options.now) || Date.now;
    if (!clientId || !region) throw new Error("clientId and region are required");
    if (!fetchFn || !storage) throw new Error("fetchFn and storage are required");

    var endpoint = "https://cognito-idp." + region + ".amazonaws.com/";
    var refreshing = null; // 同時リフレッシュを1回にまとめる

    function call(target, payload) {
      return Promise.resolve()
        .then(function () {
          return fetchFn(endpoint, {
            method: "POST",
            headers: {
              "Content-Type": "application/x-amz-json-1.1",
              "X-Amz-Target": TARGET_PREFIX + target
            },
            body: JSON.stringify(payload)
          });
        })
        .catch(function () {
          throw makeAuthError("NetworkError");
        })
        .then(function (res) {
          return Promise.resolve(res.json()).catch(function () { return {}; }).then(function (data) {
            if (!res.ok) {
              var code = String((data && data.__type) || "UnknownError").split("#").pop();
              throw makeAuthError(code, data && data.message);
            }
            return data;
          });
        });
    }

    function load() {
      var raw = storage.getItem(STORAGE_KEY);
      if (!raw) return null;
      try {
        var data = JSON.parse(raw);
        if (data && typeof data.idToken === "string" && typeof data.refreshToken === "string") return data;
      } catch (e) { /* 壊れた値は下で破棄する */ }
      storage.removeItem(STORAGE_KEY);
      return null;
    }

    function save(result, previousRefreshToken) {
      var refreshToken = result.RefreshToken || previousRefreshToken;
      var session = {
        idToken: result.IdToken,
        refreshToken: refreshToken,
        expiresAt: now() + (result.ExpiresIn || 3600) * 1000
      };
      storage.setItem(STORAGE_KEY, JSON.stringify(session));
      return session;
    }

    function handleChallengeOrResult(data) {
      if (data.AuthenticationResult) {
        save(data.AuthenticationResult);
        return { status: "signed_in" };
      }
      if (data.ChallengeName === "NEW_PASSWORD_REQUIRED") {
        var params = data.ChallengeParameters || {};
        return {
          status: "new_password_required",
          challenge: { session: data.Session, username: params.USER_ID_FOR_SRP }
        };
      }
      throw makeAuthError("UnsupportedChallenge", data.ChallengeName);
    }

    function signIn(email, password) {
      return call("InitiateAuth", {
        AuthFlow: "USER_PASSWORD_AUTH",
        ClientId: clientId,
        AuthParameters: { USERNAME: email, PASSWORD: password }
      }).then(function (data) {
        var outcome = handleChallengeOrResult(data);
        // USER_ID_FOR_SRP が無い場合は入力されたメールで応答する
        if (outcome.status === "new_password_required" && !outcome.challenge.username) {
          outcome.challenge.username = email;
        }
        return outcome;
      });
    }

    function completeNewPassword(challenge, newPassword) {
      return call("RespondToAuthChallenge", {
        ChallengeName: "NEW_PASSWORD_REQUIRED",
        ClientId: clientId,
        Session: challenge.session,
        ChallengeResponses: { USERNAME: challenge.username, NEW_PASSWORD: newPassword }
      }).then(handleChallengeOrResult);
    }

    function refresh(session) {
      if (!refreshing) {
        refreshing = call("InitiateAuth", {
          AuthFlow: "REFRESH_TOKEN_AUTH",
          ClientId: clientId,
          AuthParameters: { REFRESH_TOKEN: session.refreshToken }
        }).then(function (data) {
          return save(data.AuthenticationResult || {}, session.refreshToken).idToken;
        }).catch(function (err) {
          // 通信障害では保存を残す（再試行できる）。トークン失効などは破棄してログインへ戻す
          if (err.code === "NetworkError") throw err;
          storage.removeItem(STORAGE_KEY);
          return null;
        }).then(function (value) {
          refreshing = null;
          return value;
        }, function (err) {
          refreshing = null;
          throw err;
        });
      }
      return refreshing;
    }

    function getIdToken(opts) {
      var session = load();
      if (!session) return Promise.resolve(null);
      var force = !!(opts && opts.forceRefresh);
      if (!force && session.expiresAt - now() > EXPIRY_MARGIN_MS) {
        return Promise.resolve(session.idToken);
      }
      return refresh(session);
    }

    function signOut() { storage.removeItem(STORAGE_KEY); }
    function isSignedIn() { return load() !== null; }

    return {
      signIn: signIn,
      completeNewPassword: completeNewPassword,
      getIdToken: getIdToken,
      signOut: signOut,
      isSignedIn: isSignedIn
    };
  }

  return { createAuth: createAuth, AuthError: AuthError };
});
