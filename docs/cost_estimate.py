"""ExpireGuard の月額コスト試算（1人が1か月使う場合）。

実行: python3 docs/cost_estimate.py
単価は 2026-11-15 に AWS Price List API（us-east-1）で取得した値。
Bedrock の Nova 2 Lite と Scheduler と Amplify は Price List で取れなかったため、公表単価の仮定を使う。
無料利用枠は含めない（定価の合計）。
"""

from __future__ import annotations

USD_JPY = 150.0  # 為替の仮定

# ---- 利用量の仮定（1人・1か月） ----
EXTRACTIONS = 20          # スクショの読み取り回数
API_CALLS = 150           # ダッシュボード表示や登録・削除などのAPI呼び出し（/extract を除く）
NOTIFY_RUNS = 30          # 日次の通知判定
EMAILS = 10               # 送信するメール数
PAGE_LOADS = 60           # 画面の読み込み
PAGE_MB = 0.2             # 1回の読み込みで配信するデータ量（MB）
IMAGE_MB = 0.5            # スクショ1枚のサイズ（MB）
IMAGE_DAYS = 7            # S3に残る日数（ライフサイクル）
LOG_KB_PER_INVOCATION = 1.0

# Bedrock（Nova 2 Lite）。1回の読み取りあたりのトークン数の仮定
INPUT_TOKENS = 3000       # 画像＋プロンプト
OUTPUT_TOKENS = 500       # JSON（2ロット程度）

# ---- 単価（USD） ----
PRICE = {
    # Price List API で確認した値（us-east-1）
    "lambda_gb_s_arm": 0.0000133334,
    "lambda_request": 0.0000002,
    "apigw_http_request": 0.000001,
    "ddb_write_unit": 0.000000625,
    "ddb_read_unit": 0.000000125,
    "ddb_pitr_gb_month": 0.20,
    "s3_gb_month": 0.023,
    "s3_put": 0.000005,
    "s3_get": 0.0000004,
    "ses_email": 0.00016,   # Price List の Essentials-Outbound-Email
    "cognito_essentials_mau": 0.015,
    "logs_gb_ingest": 0.50,
    # 公表単価の仮定（Price List で取得できなかったもの）
    "scheduler_invocation": 0.000001,   # 100万回あたり1.00 USD
    "amplify_gb_served": 0.15,
    "amplify_gb_month_stored": 0.023,
}
# Nova 2 Lite の単価（USD / 100万トークン）。公表値は入力 0.30 / 出力 2.50（グローバル）。
# 米国の推論プロファイルは割増の可能性があるため、上限として約1.3倍も計算する。
NOVA = {"公表値": (0.30, 2.50), "上限（約1.3倍）": (0.40, 3.30)}


def estimate(nova_in: float, nova_out: float) -> dict[str, float]:
    lambda_gb_s = (
        EXTRACTIONS * 2.2 * 0.5      # extract: 実測の平均 約2.2秒、512MB
        + API_CALLS * 0.1 * 0.25     # api: 約0.1秒、256MB
        + NOTIFY_RUNS * 1.0 * 0.25   # notify: 約1秒、256MB
    )
    invocations = EXTRACTIONS + API_CALLS + NOTIFY_RUNS
    image_gb_month = EXTRACTIONS * IMAGE_MB / 1024 * (IMAGE_DAYS / 30)
    return {
        "Bedrock（Nova 2 Lite）": EXTRACTIONS * (INPUT_TOKENS * nova_in + OUTPUT_TOKENS * nova_out) / 1_000_000,
        "Amazon Cognito": 1 * PRICE["cognito_essentials_mau"],
        "Amazon SES": EMAILS * PRICE["ses_email"],
        "AWS Amplify Hosting": PAGE_LOADS * PAGE_MB / 1024 * PRICE["amplify_gb_served"]
        + 0.001 * PRICE["amplify_gb_month_stored"],
        "AWS Lambda": lambda_gb_s * PRICE["lambda_gb_s_arm"] + invocations * PRICE["lambda_request"],
        "Amazon API Gateway": (EXTRACTIONS + API_CALLS) * PRICE["apigw_http_request"],
        "Amazon DynamoDB": 80 * PRICE["ddb_write_unit"] + 250 * PRICE["ddb_read_unit"]
        + 0.00001 * PRICE["ddb_pitr_gb_month"],
        "Amazon S3": EXTRACTIONS * (PRICE["s3_put"] + PRICE["s3_get"]) + image_gb_month * PRICE["s3_gb_month"],
        "CloudWatch Logs": invocations * LOG_KB_PER_INVOCATION / 1024 / 1024 * PRICE["logs_gb_ingest"],
        "EventBridge Scheduler": NOTIFY_RUNS * PRICE["scheduler_invocation"],
    }


if __name__ == "__main__":
    for label, (nin, nout) in NOVA.items():
        rows = estimate(nin, nout)
        total = sum(rows.values())
        print(f"## Nova 2 Lite 単価: {label}（入力 {nin} / 出力 {nout} USD per 100万トークン）")
        for name, usd in sorted(rows.items(), key=lambda kv: -kv[1]):
            print(f"  {name:26} {usd:9.5f} USD  {usd * USD_JPY:7.2f} 円")
        print(f"  {'合計':24} {total:9.5f} USD  {total * USD_JPY:7.2f} 円（1 USD = {USD_JPY:.0f} 円）\n")
    # 参考: Cognito が無料利用枠に収まる場合
    rows = estimate(*NOVA["公表値"])
    print(f"参考: Cognito を無料とした場合（公表値）: {(sum(rows.values()) - rows['Amazon Cognito']) * USD_JPY:.2f} 円")
