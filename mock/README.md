# ExpireGuard モック（S3 の静的サイトだけ）

公開用のデモです。バックエンドもログインもなく、ブラウザの中だけで動きます。

- ログインは不要。最初からログイン後の画面（ダッシュボード）が開く
- 「Add screenshot」でファイルを選ぶと、**ファイルは読まずに捨て**、画像の内容と無関係な固定のサンプルが読み取り結果として出る
- 1回目はポイント2件（期間限定）、2回目はサブスク1件、3回目はまたポイント、と交互に出る
- 確認画面で保存すると、ダッシュボードと一覧に反映される。手入力、「使った」、削除も動く
- データはメモリ上だけ。**ページを読み込み直すと消える**。DynamoDB にも S3 にも書かない
- 「Send test notification」は、メールを送らず、「デモ版のため送信されません」と表示する
- サンプルのサービス名は「Sample Points」「Sample Streaming」で、実在のブランド名は使わない

本物のアプリ（`../app`）の `index.html` と `app.js` を土台にしています。`app.js` の変更は、テスト通知の文言4行だけです。

## 構成

```
mock/
├── src/mock-backend.js   API の代わり（メモリ上。fetch の差し替えも含む）
├── src/auth-stub.js      ログインの代わり（常にログイン済み）
├── build.mjs             本物のフロントから、公開用の site/ を組み立てる
├── tests/                node:test（27件）
├── template.yaml         S3（非公開）と CloudFront（HTTPS 配信）
└── site/                 build.mjs の出力（アップロードするもの）
```

## 手元で確認する

```bash
node --test mock/tests/*.test.mjs     # テスト（Node 18 以上、依存なし）
node mock/build.mjs                   # site/ を生成
python3 -m http.server 8765 --directory mock/site
# ブラウザで http://localhost:8765/ を開く
```

## 公開する（us-east-1）

S3 のバケットは非公開で、CloudFront（OAC）からだけ読める。公開URLは HTTPS で、HTTP は HTTPS へ転送される。

```bash
cd mock
aws cloudformation deploy --template-file template.yaml --stack-name expireguard-mock --region us-east-1
aws cloudformation describe-stacks --stack-name expireguard-mock --region us-east-1 \
  --query 'Stacks[0].Outputs' --output table      # BucketName / DistributionId / SiteURL

node build.mjs
aws s3 sync site/ "s3://<BucketName>" --delete --cache-control 'max-age=300' --region us-east-1
aws cloudfront create-invalidation --distribution-id <DistributionId> --paths '/*'
# SiteURL を開いて確認する
```

現在の公開URL: https://d3s3h2s5booe20.cloudfront.net

## 注意

- 公開するのはモックの HTML と JS だけで、本物の API の URL、ユーザープール、メールアドレス、アカウント ID は入っていない（`tests/build.test.mjs` で検査している）
- CSP（ページ内の設定）で、モック以外のURLへの通信を止めている。アップロードしたファイルは、どこにも送られない
- CloudFront の標準の証明書（`*.cloudfront.net`）を使うため、独自ドメインと TLS の最小バージョンの指定はしていない
- 公開をやめるときは、バケットを空にしてからスタックを削除する

```bash
aws s3 rm "s3://<BucketName>" --recursive --region us-east-1
aws cloudformation delete-stack --stack-name expireguard-mock --region us-east-1
```
