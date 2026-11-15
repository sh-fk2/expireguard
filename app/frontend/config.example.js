// デプロイ後に config.js として保存する（config.js は .gitignore 対象）。
// apiBaseUrl      : `sam deploy` の出力 ApiUrl
// userPoolClientId: `sam deploy` の出力 UserPoolClientId（シークレットなしのアプリクライアント）
// region          : Cognito ユーザープールのリージョン（us-east-1 固定）
window.EXPIREGUARD_CONFIG = {
  apiBaseUrl: "https://<api-id>.execute-api.us-east-1.amazonaws.com",
  userPoolClientId: "<user-pool-client-id>",
  region: "us-east-1"
};
