# ExpireGuard（実装）

ポイント・クーポンの失効と、サブスクの自動課金を、スクリーンショットだけで登録して期限前にメールで知らせるサーバーレスアプリです。
Weekend Challenge「No Pipeline, No Problem」向けで、CI/CD パイプラインは持たず、ローカルから `sam deploy` するだけで構築します。

デプロイ手順の英語版は、リポジトリ直下の `../README.md` にあります。

## 構成

| 区分 | 内容 |
|---|---|
| リージョン | `us-east-1` 固定（テンプレートの Rules で他リージョンへのデプロイを拒否） |
| IaC | AWS SAM（`template.yaml` 1本） |
| API | API Gateway HTTP API ＋ Lambda 3関数（`api` / `extract` / `notify`） |
| データ | DynamoDB 1テーブル（下書きは TTL で7日後に自動削除）、S3（画像は7日で自動削除） |
| 抽出 | Bedrock Converse API（Claude の画像入力）。プロンプトは `src/extract/prompts.py` |
| 通知 | EventBridge Scheduler（毎日 09:00 JST）＋ SES v2 |
| フロント | 素の HTML/JS（`frontend/`）。Amplify Hosting に手動デプロイ |
| 認証 | Amazon Cognito ユーザープール＋ HTTP API の JWT オーソライザー。管理者がユーザーを作成する（セルフサインアップ無効）。詳細は「認証」参照 |

```
app/
├── template.yaml        SAM テンプレート
├── samconfig.toml       リージョン等の既定値（メールアドレスは含めない）
├── src/
│   ├── common/          日付・検証・DynamoDB・クライアント生成
│   ├── api/             CRUD・/summary・/uploads
│   ├── extract/         Bedrock 抽出（プロンプト・応答解釈）
│   └── notify/          日次判定・メール組み立て・テスト通知
├── tests/               pytest（moto で AWS をモック、Bedrock・SES 送信はスタブ）
├── frontend/            index.html / app.js / auth.js / config.example.js
└── frontend-tests/      auth.js の単体テスト（node:test、依存なし）
```

### API

全ルートが Cognito の IdToken（`Authorization: Bearer <IdToken>`）必須です。CORS のプリフライト（OPTIONS）は HTTP API が自動応答するため認証不要です。

| メソッド | パス | Lambda |
|---|---|---|
| GET | /summary | api |
| GET / POST | /items | api |
| PATCH / DELETE | /items/{id} | api |
| POST | /uploads | api（S3 署名付き POST。3.75MB 上限・PNG/JPEG のみ） |
| POST | /extract | extract |
| POST | /notify/test | notify（呼び出しユーザー分のみ対象） |

> `/notify/test` は、IAM を増やさず最小権限を保つため、api Lambda を経由せず HTTP API から notify Lambda へ直接ルーティングしています。

## 前提条件

- Python 3.12、AWS SAM CLI、AWS CLI v2、`aws login` 済みのデフォルトプロファイル
- 実際のメールアドレスは **リポジトリに書かない**。デプロイ時のパラメータで渡す

## ローカル検証（デプロイ不要）

```bash
cd app
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/pytest                     # テスト＋カバレッジ（80%未満で失敗）
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/bandit -c pyproject.toml -r src
node --test frontend-tests/*.test.mjs   # フロント認証モジュールのテスト（Node 18 以上）
sam validate --lint --region us-east-1
sam build --region us-east-1
```

## ユーザーが行う事前作業（承認が必要なため実行していません）

### 1. Bedrock のモデルを使えるようにする

1. `us-east-1` の Bedrock コンソールで、使用するモデル（既定は Amazon Nova 2 Lite の `us.amazon.nova-2-lite-v1:0`）が利用可能か確認する。Claude を使う場合は `BedrockModelId` に `us.anthropic.claude-sonnet-4-6` を指定し、初回に Anthropic の利用目的の入力などが求められたら完了させる。PayPay の実スクショ（通常ポイントと期間限定ポイントの2レコード）では Nova 2 Lite で正しく読み取れた
2. 別のモデルを使う場合は、画像入力に対応するモデルの推論プロファイル ID を `BedrockModelId` で渡す（確認コマンド例）

```bash
aws bedrock list-inference-profiles --region us-east-1 --type-equals SYSTEM_DEFINED \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'anthropic.claude')].inferenceProfileId"
```

### 2. SES で送信元・宛先を認証する

サンドボックスでは送信元と宛先の**両方**の認証が必要です。

```bash
aws sesv2 create-email-identity --email-address '<送信元アドレス>' --region us-east-1
aws sesv2 create-email-identity --email-address '<宛先アドレス>' --region us-east-1
```

届いた認証メールのリンクを開き、次で `VerifiedForSendingStatus` が `true` になることを確認します。

```bash
aws sesv2 get-email-identity --email-identity '<アドレス>' --region us-east-1 \
  --query VerifiedForSendingStatus
```

> ドメイン単位で認証している場合、テンプレートの IAM（`ses:SendEmail`）はメールアドレスのアイデンティティ ARN に限定しているため、メールアドレス単位で認証してください。

### 3. デプロイ（`sam deploy`）

変更セットの確認（`confirm_changeset = true`）で、作成されるリソースと IAM を確認してから承認します。

```bash
cd app
sam build --region us-east-1
sam deploy \
  --parameter-overrides \
    SenderEmail='<送信元アドレス>' \
    RecipientEmail='<宛先アドレス>'
# モデルを変える場合: BedrockModelId='us.anthropic.claude-haiku-4-5-20251001-v1:0' を追加
```

作成される主なリソース: DynamoDB、S3、HTTP API、Lambda×3（IAM ロール含む）、Scheduler、CloudWatch Logs、Amplify アプリ、Cognito ユーザープールとアプリクライアント。

> **既存スタックの更新時の注意**: 認証追加の変更セットには、Cognito の `UserPool` / `UserPoolClient` の追加、`HttpApi` の更新（JWT オーソライザーを全ルートに適用）、3つの Lambda 用 IAM ポリシーの更新（S3 を `uploads/*` へ、notify に `dynamodb:Scan` を追加）が含まれます。`ItemsTable`・`ScreenshotBucket`・`AmplifyApp` の置換や削除が出ていないことを確認してから承認してください。**デプロイ直後からは未認証の API 呼び出しが 401 になるため、次の「ユーザー作成」と「フロント配置」を続けて行ってください。**

### 3-1. ユーザーを作成する（認証）

セルフサインアップは無効です。利用者は管理者が作成します。`UserPoolId` はスタック出力から取得します。
メールアドレスとパスワードは、シェルのヒストリやリポジトリに残さないよう、プレースホルダーを自分の値に置き換えて実行してください。

```bash
STACK=expireguard; REGION=us-east-1
POOL_ID=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)

# 1. ユーザー作成（招待メールは送らない）。メールアドレスがユーザー名になる
aws cognito-idp admin-create-user --user-pool-id "$POOL_ID" --region "$REGION" \
  --username '<利用者のメールアドレス>' \
  --user-attributes Name=email,Value='<利用者のメールアドレス>' Name=email_verified,Value=true \
  --message-action SUPPRESS

# 2. パスワードを設定する（--permanent を付けると初回の変更が不要。付けなければ一時パスワード）
aws cognito-idp admin-set-user-password --user-pool-id "$POOL_ID" --region "$REGION" \
  --username '<利用者のメールアドレス>' --password '<12文字以上・大小英字・数字・記号を含む>' \
  --permanent
```

- `--permanent` を付けない場合、ユーザーは `FORCE_CHANGE_PASSWORD` 状態になり、**初回ログイン時に画面の「新しいパスワードの設定」へ進みます**（NEW_PASSWORD_REQUIRED チャレンジ）。
- パスワードポリシーは 12 文字以上で、英大文字・英小文字・数字・記号を必須にしています。
- ユーザーの一覧・削除: `aws cognito-idp list-users` / `admin-delete-user`。

### 4. フロントを Amplify に配置する（手動デプロイ）

```bash
STACK=expireguard; REGION=us-east-1
out() { aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }

# config.js を生成する（.gitignore 対象。API の URL・アプリクライアント ID・リージョンのみで、秘密情報は含まない）
cat > frontend/config.js <<EOF
window.EXPIREGUARD_CONFIG = {
  apiBaseUrl: "$(out ApiUrl)",
  userPoolClientId: "$(out UserPoolClientId)",
  region: "$REGION"
};
EOF
(cd frontend && zip -q ../web.zip index.html app.js auth.js config.js)

APP_ID=$(out AmplifyAppId)
aws amplify create-deployment --app-id "$APP_ID" --branch-name main --region "$REGION"
# 出力の zipUploadUrl と jobId を使う
curl -s --upload-file web.zip '<zipUploadUrl>'
aws amplify start-deployment --app-id "$APP_ID" --branch-name main --job-id '<jobId>' --region "$REGION"
```

公開 URL はスタック出力 `SiteUrl`（`https://main.<DefaultDomain>`）です。

### 5. 動作確認

1. `SiteUrl` を開く → 作成したユーザーでログイン → 「Add screenshot」でスクショを選ぶ → 確認画面で修正して保存
2. ダッシュボードに失効リスク合計と一覧が出ることを確認
3. 「Send test notification」を押し、宛先にメールが届くことを確認
4. 抽出が空になる場合は CloudWatch Logs（`ExtractFunction`）で Bedrock のエラーを確認する

## 認証

| 項目 | 内容 |
|---|---|
| ユーザー管理 | Cognito ユーザープール。`AdminCreateUserOnly`（セルフサインアップ無効）。メールアドレスがユーザー名。パスワード再設定は管理者のみ |
| アプリクライアント | シークレットなし。`ALLOW_USER_PASSWORD_AUTH` と `ALLOW_REFRESH_TOKEN_AUTH` のみ有効。IdToken・アクセストークン 60 分、リフレッシュトークン 30 日 |
| API の保護 | HTTP API の JWT オーソライザー（`$request.header.Authorization`）を既定にし、全ルートに適用。issuer はこのユーザープール、audience はこのアプリクライアント。**IdToken** を送る（アクセストークンは audience が合わず拒否される） |
| ユーザー識別 | 各 Lambda は `requestContext.authorizer.jwt.claims.sub` を `userId` に使う。`sub` が無い・不正な値のリクエストは 401。リクエスト本文の `userId` は無視する |
| データ分離 | DynamoDB はパーティションキー `userId` で自分の分だけ読み書き。他ユーザーの `itemId` は 404（存在の有無を漏らさない） |
| 画像の分離 | アップロード先は `uploads/<sub>/`。`/extract` は自分のプレフィックス配下のキー以外を 400 で拒否し、S3 を読まない（IAM は `uploads/*` だが、ユーザー単位の制限は IAM で表現できないためコードで強制） |
| 日次通知 | EventBridge Scheduler 起動時は全ユーザー分を走査して判定し、宛先は従来どおり `RecipientEmail`（SES サンドボックスのため単一）。複数ユーザー分は 1 通にまとまる。ステージ記録はアイテムの持ち主ごと |
| テスト通知 | `POST /notify/test` は呼び出しユーザー分のみが対象 |

フロント（`frontend/auth.js`）は SDK を使わず、Cognito の `InitiateAuth`（USER_PASSWORD_AUTH）と `RespondToAuthChallenge` を `fetch` で直接呼びます。

- トークンは `sessionStorage` に保存（タブを閉じると消える）。保存するのは IdToken とリフレッシュトークンのみ
- IdToken は期限の 60 秒前に、リフレッシュトークンで自動更新する。API が 401 を返したら強制更新して 1 回だけ再試行し、それでも失敗すればログイン画面へ戻す
- 初回ログインで NEW_PASSWORD_REQUIRED が返った場合は、新パスワードの設定画面へ進む
- 画面の動的な値は `textContent` で挿入し、HTML として解釈しない

## 要件トレーサビリティ

| 機能（先頭の数字は内部の要件番号） | 実装 | テスト |
|---|---|---|
| 1.1, 1.3 アップロード・画像のみ | `api/uploads.py`、`extract/handler.py` | `test_api_uploads.py`、`test_extract.py` |
| 2.x ポイント抽出 | `extract/prompts.py`、`extract/parser.py` | `test_extract.py` |
| 3.x サブスク抽出 | 同上（ポイントが空なら再試行） | `test_extract.py` |
| 4.x 確認・修正・登録 | `POST /items`（`draftId` で下書きを確定）、`frontend/app.js` | `test_api_items.py`、`test_models.py` |
| 5.x 手入力 | `frontend/app.js`、`POST /items` | 同上 |
| 6.x ダッシュボード | `api/summary.py`、`frontend/app.js` | `test_api_summary.py` |
| 7.x 管理（更新・使った・解約・削除） | `api/handler.py` | `test_api_items.py` |
| 8.x ポイント通知 | `notify/logic.py`、`notify/mailer.py` | `test_notify.py` |
| 9.x サブスク通知・日付繰り上げ | 同上、`common/dates.py` | `test_notify.py`、`test_dates.py` |
| 10.x テスト通知 | `notify/handler.py` | `test_notify.py` |
| 11.x サーバーレス・7日削除 | `template.yaml` | `sam validate --lint` |
| 12.x 多言語（既定 EN、言語を記憶） | `frontend/app.js` | 手動確認 |
| 認証・ユーザー分離（追加要件） | `common/auth.py`、各 handler、`template.yaml`、`frontend/auth.js` | `test_auth.py`、`test_user_isolation.py`、`test_template_auth.py`、`frontend-tests/auth.test.mjs` |

## 仕様の解釈と既知の制約

- 守れた金額は、使用済み・解約済みの `amount` の合計（用語定義と画面ラベルに従い、サブスクは1周期分）
- 失効済み（期限が過去）のポイントは失効リスク合計に含めない
- 通知は「残日数がちょうど 30/14/7/1（サブスクは 7/3/1）日の日」だけ送る。Lambda や SES が停止した日は、その日のステージを送れない
- 月次サブスクの更新日を月末丸め（例: 1/31 → 2/28）で繰り上げると、以後は 28 日基準になる
- HTTP API の統合タイムアウトは30秒。Bedrock が遅いと `/extract` が 503 になり、画面は空の確認フォーム（手入力）に落ちる。Haiku 系へ変えると短縮できる
- 通知メールの言語は日本語固定（設計書 UI の将来拡張）
- アイテムの編集 UI（アイテム詳細画面）は未実装。API（PATCH）は実装・テスト済み
- 認証は `USER_PASSWORD_AUTH`（パスワードを Cognito へ直接送る方式）。MFA は未対応で、`sessionStorage` のトークンは XSS が起きれば読み取られる。公開運用では MFA・SRP・HttpOnly Cookie 方式の検討が必要
- Cognito のメール送信は既定（Cognito 標準）の送信元・上限のまま。招待メールは使わず、管理者がパスワードを設定する運用
- `UserPool` は `DeletionPolicy: Retain`。スタックを削除してもユーザープールは残るため、不要なら手動で削除する
- 日次通知は DynamoDB の Scan で全ユーザー分を読む。ユーザー数・件数が増えた場合は GSI などへの見直しが必要
- API 全体と `POST /notify/test` のスロットリングは認証後も維持している
