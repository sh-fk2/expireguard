"""extract Lambda のテスト（要件 1.4, 2.1〜2.5, 3.1〜3.4）。Bedrock はスタブ。"""

import json
from datetime import timedelta

import boto3
import pytest
from botocore.exceptions import ClientError

from conftest import BUCKET, body_of, make_event
from extract import prompts
from extract.handler import lambda_handler
from extract.parser import normalize_points, parse_model_json

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
KEY = "uploads/demo-user/abc.png"

PAYPAY = {
    "service": "PayPayポイント",
    "lots": [
        {"points": 460, "expiryDate": None, "isLimited": False},
        {"points": 114, "expiryDate": "2026-12-31", "isLimited": True},
    ],
}


def _put(data=PNG, key=KEY):
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=key, Body=data)


def _call(key=KEY):
    return lambda_handler(make_event("POST /extract", {"key": key}), None)


def test_ポイント用プロンプトは合計行を除外し期間限定の表記でフラグを決める():
    # Nova が「期間限定ポイントの合計」を通常ポイントとして出した事例の再発防止
    assert "合計" in prompts.POINTS_PROMPT
    assert "lotsに含めない" in prompts.POINTS_PROMPT
    assert "「期間限定」と書かれたポイントは isLimited を true" in prompts.POINTS_PROMPT


def test_サービス名末尾の期間限定表記は取り除く():
    # モデルが「PayPayポイント（期間限定）」のように返しても isLimited で表すため、名称には残さない
    data = {
        "service": "PayPayポイント（期間限定）",
        "lots": [{"points": 114, "expiryDate": "2026-12-31", "isLimited": True}],
    }
    lots = normalize_points(data)
    assert lots[0]["service"] == "PayPayポイント"
    assert lots[0]["isLimited"] is True


def test_確定版プロンプトが設計メモ通り():
    assert prompts.POINTS_PROMPT.startswith(
        "この画像はポイントプログラムの残高画面のスクリーンショットです。"
    )
    assert (
        '{"service": "サービス名", "lots": [{"points": 数字, "expiryDate": "YYYY-MM-DD", "isLimited": true/false}]}'
        in prompts.POINTS_PROMPT
    )
    assert "- ポイント数が読み取れないロットは含めない" in prompts.POINTS_PROMPT
    assert "- 期限の年が読み取れない場合は null にする" in prompts.POINTS_PROMPT
    assert prompts.SUBSCRIPTION_PROMPT.startswith(
        "この画像はサブスクリプションの契約・一覧画面のスクリーンショットです。"
    )
    assert "複数のサービスが一覧で写っている場合は、配列で全件返す" in prompts.SUBSCRIPTION_PROMPT


def test_ポイント画像はロットごとに下書き保存して返す(aws, repo, today, make_bedrock):
    _put()
    stub = make_bedrock([json.dumps(PAYPAY, ensure_ascii=False)])
    res = _call()
    assert res["statusCode"] == 200
    body = body_of(res)
    assert body["extracted"] is True
    assert body["sourceImageKey"] == KEY
    items = body["items"]
    assert [i["points"] for i in items] == [460, 114]
    assert items[0]["expiryDate"] is None
    assert items[1]["expiryDate"] == "2026-12-31"
    assert items[1]["isLimited"] is True
    assert all(i["status"] == "draft" and i["kind"] == "points" for i in items)
    assert all(i["amount"] == i["points"] for i in items)
    stored = repo.get("demo-user", items[1]["itemId"])
    assert stored["status"] == "draft"
    assert stored["sourceImageKey"] == KEY
    assert stored["ttl"] > 0
    assert len(stub.calls) == 1


def test_Bedrockにはconverse形式で画像とモデルIDを渡す(aws, today, make_bedrock):
    _put()
    stub = make_bedrock([json.dumps(PAYPAY)])
    _call()
    call = stub.calls[0]
    assert call["modelId"] == "us.anthropic.claude-sonnet-4-6"
    content = call["messages"][0]["content"]
    assert content[0]["image"]["format"] == "png"
    assert content[0]["image"]["source"]["bytes"] == PNG
    assert content[1]["text"] == prompts.POINTS_PROMPT
    assert call["inferenceConfig"]["temperature"] == 0


def test_JPEGはjpeg形式で渡す(aws, today, make_bedrock):
    key = "uploads/demo-user/x.jpg"
    _put(JPEG, key)
    stub = make_bedrock([json.dumps(PAYPAY)])
    _call(key)
    assert stub.calls[0]["messages"][0]["content"][0]["image"]["format"] == "jpeg"


def test_前後に説明文やコードフェンスがあってもJSONを切り出す(aws, today, make_bedrock):
    _put()
    make_bedrock(["読み取り結果です。\n```json\n" + json.dumps(PAYPAY) + "\n```\n以上"])
    assert len(body_of(_call())["items"]) == 2


def test_ポイント数のないロットは除外し日付は正規化する(aws, today, make_bedrock):
    _put()
    raw = {
        "service": "楽天ポイント",
        "lots": [
            {"points": None, "expiryDate": "2026-12-31", "isLimited": False},
            {"points": 0, "expiryDate": "2026-12-31", "isLimited": False},
            {"points": "1,240", "expiryDate": "2026-02-30", "isLimited": "true"},
        ],
    }
    make_bedrock([json.dumps(raw)])
    items = body_of(_call())["items"]
    assert len(items) == 1
    assert items[0]["points"] == 1240
    assert items[0]["expiryDate"] is None  # 不正な日付は推測せず null


def test_ポイントが空ならサブスク用プロンプトで再試行する(aws, repo, today, make_bedrock):
    _put()
    sub = [
        {
            "service": "Netflix",
            "amount": 1590,
            "nextRenewalDate": "2026-11-20",
            "cycle": "monthly",
            "trialEndDate": None,
        },
        {
            "service": "Spotify",
            "amount": 980,
            "nextRenewalDate": "2026-12-01",
            "cycle": "yearly",
            "trialEndDate": "2026-11-25",
        },
    ]
    stub = make_bedrock([json.dumps({"service": None, "lots": []}), json.dumps(sub)])
    body = body_of(_call())
    assert len(stub.calls) == 2
    assert stub.calls[1]["messages"][0]["content"][1]["text"] == prompts.SUBSCRIPTION_PROMPT
    netflix, spotify = body["items"]
    assert netflix["kind"] == "subscription"
    assert netflix["amount"] == 1590
    assert netflix["expiryDate"] == "2026-11-20"
    assert netflix["cycle"] == "monthly"
    assert "points" not in netflix
    # トライアル終了日は課金開始日（次回更新日）として扱う
    assert spotify["expiryDate"] == "2026-11-25"
    assert repo.get("demo-user", spotify["itemId"])["status"] == "draft"


def test_サブスクが単一オブジェクトで返っても読める(aws, today, make_bedrock):
    _put()
    sub = {
        "service": "Netflix",
        "amount": 1590,
        "nextRenewalDate": "2026-11-20",
        "cycle": "weekly",
        "trialEndDate": None,
    }
    make_bedrock([json.dumps({"service": None, "lots": []}), json.dumps(sub)])
    items = body_of(_call())["items"]
    assert len(items) == 1
    assert items[0]["cycle"] is None  # 不正な周期は推測しない


def test_サブスクで金額もサービス名もない要素は除外する(aws, today, make_bedrock):
    _put()
    make_bedrock([json.dumps({"lots": []}), json.dumps([{"service": None, "amount": None}])])
    body = body_of(_call())
    assert body["items"] == []
    assert body["extracted"] is False


def test_どちらも空なら例外にせず空結果を返す(aws, repo, today, make_bedrock):
    _put()
    make_bedrock([json.dumps({"lots": []}), json.dumps([])])
    res = _call()
    assert res["statusCode"] == 200
    assert body_of(res) == {"items": [], "extracted": False, "sourceImageKey": KEY}


def test_JSONでない応答は抽出なしとして扱う(aws, today, make_bedrock):
    _put()
    make_bedrock(["読み取れませんでした", "やはり読めません"])
    body = body_of(_call())
    assert body["items"] == [] and body["extracted"] is False


def test_Bedrockエラーでも200で空結果(aws, today, make_bedrock):
    _put()
    err = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "x"}}, "Converse")
    make_bedrock([err])
    res = _call()
    assert res["statusCode"] == 200
    assert body_of(res)["extracted"] is False


@pytest.mark.parametrize(
    "key", ["", "../etc/passwd", "uploads/other/x.png", "uploads/demo-user/../x.png", 5, None]
)
def test_不正なキーは400(aws, today, make_bedrock, key):
    stub = make_bedrock([])
    res = lambda_handler(make_event("POST /extract", {"key": key}), None)
    assert res["statusCode"] == 400
    assert stub.calls == []


def test_S3にない画像は404(aws, today, make_bedrock):
    make_bedrock([])
    assert _call()["statusCode"] == 404


def test_画像でないデータは400(aws, today, make_bedrock):
    _put(b"%PDF-1.7 not image")
    stub = make_bedrock([])
    res = _call()
    assert res["statusCode"] == 400
    assert stub.calls == []


def test_大きすぎる画像は400(aws, today, make_bedrock):
    _put(PNG + b"0" * 3_750_000)
    assert _call()["statusCode"] == 400


def test_壊れたJSON本文は400(aws, today):
    res = lambda_handler(make_event("POST /extract", raw_body="{"), None)
    assert res["statusCode"] == 400


def test_下書きのttlは約7日後(aws, repo, today, make_bedrock):
    _put()
    make_bedrock([json.dumps(PAYPAY)])
    item = body_of(_call())["items"][0]
    stored = repo.get("demo-user", item["itemId"])
    from datetime import UTC, datetime

    delta = datetime.fromtimestamp(int(stored["ttl"]), UTC) - datetime.now(UTC)
    assert timedelta(days=6) < delta < timedelta(days=8)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('前置き {"a": 1} 後書き', {"a": 1}),
        ('[{"a": 1}]', [{"a": 1}]),
        ("no json", None),
        ("{broken", None),
        ("", None),
    ],
)
def test_parse_model_json(text, expected):
    assert parse_model_json(text) == expected
