/* モック用のログインの代用（素の JS）。常にログイン済みとして扱い、トークンは固定の文字列を返す。
 * 本物の frontend/auth.js と同じ名前（window.ExpireGuardAuth）で公開するので、app.js は変更しない。
 * あわせて、fetch をモックのバックエンドに差し替える（API とアップロード先は応答し、他のURLへは通信しない）。 */
(function () {
  "use strict";
  var config = window.EXPIREGUARD_CONFIG || {};

  window.ExpireGuardMock.installMock(window, {
    apiBase: config.apiBaseUrl,
    backend: window.ExpireGuardMock.createMockBackend()
  });

  function AuthError(code, message) {
    this.name = "AuthError";
    this.code = code;
    this.message = message;
  }
  AuthError.prototype = Object.create(Error.prototype);

  function createAuth() {
    return {
      signIn: function () { return Promise.resolve({ status: "signedIn" }); },
      completeNewPassword: function () { return Promise.resolve({ status: "signedIn" }); },
      getIdToken: function () { return Promise.resolve("mock-token"); },
      signOut: function () {},
      isSignedIn: function () { return true; }
    };
  }

  window.ExpireGuardAuth = { createAuth: createAuth, AuthError: AuthError };
})();
