"""ユーザー分離のテスト: 他ユーザーのデータ・S3 キーに触れないこと。"""

from __future__ import annotations

import boto3
import pytest

from api.handler import lambda_handler as api_handler
from conftest import BUCKET, DEFAULT_SUB, OTHER_SUB, body_of, make_event
from extract.handler import lambda_handler as extract_handler
from notify.handler import lambda_handler as notify_handler

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
POINTS_BODY = {
    "kind": "points",
    "service": "楽天ポイント",
    "points": 100,
    "expiryDate": "2026-12-01",
    "isLimited": False,
}


# ---------------------------------------------------------------- アイテムの分離
def test_GET_itemsは自分のアイテムだけ返す(aws, seed, today):
    seed(itemId="mine")
    seed(itemId="theirs", userId=OTHER_SUB)
    res = api_handler(make_event("GET /items"), None)
    assert [i["itemId"] for i in body_of(res)["items"]] == ["mine"]


def test_GET_summaryは自分のアイテムだけ集計する(aws, seed, today):
    seed(itemId="mine", amount=100, points=100)
    seed(itemId="theirs", userId=OTHER_SUB, amount=9999, points=9999)
    body = body_of(api_handler(make_event("GET /summary"), None))
    assert body["atRiskAmount"] == 100
    assert [i["itemId"] for i in body["items"]] == ["mine"]


def test_PATCH_itemsは他ユーザーのIDを404にし変更しない(aws, repo, seed, today):
    seed(itemId="theirs", userId=OTHER_SUB, points=5)
    res = api_handler(make_event("PATCH /items/{id}", {"points": 1}, {"id": "theirs"}), None)
    assert res["statusCode"] == 404
    assert repo.get(OTHER_SUB, "theirs")["points"] == 5


def test_DELETE_itemsは他ユーザーのIDを404にし削除しない(aws, repo, seed, today):
    seed(itemId="theirs", userId=OTHER_SUB)
    res = api_handler(make_event("DELETE /items/{id}", None, {"id": "theirs"}), None)
    assert res["statusCode"] == 404
    assert repo.get(OTHER_SUB, "theirs") is not None


def test_POST_itemsは他ユーザーの下書きを確定できない(aws, repo, seed, today):
    seed(itemId="d-theirs", userId=OTHER_SUB, status="draft")
    res = api_handler(make_event("POST /items", {**POINTS_BODY, "draftId": "d-theirs"}), None)
    assert res["statusCode"] == 404
    assert repo.get(OTHER_SUB, "d-theirs")["status"] == "draft"


def test_POST_itemsは呼び出しユーザーのsubで保存する(aws, repo, today):
    res = api_handler(make_event("POST /items", POINTS_BODY, sub=OTHER_SUB), None)
    item = body_of(res)
    assert item["userId"] == OTHER_SUB
    assert repo.get(OTHER_SUB, item["itemId"]) is not None
    assert repo.get(DEFAULT_SUB, item["itemId"]) is None


def test_ボディのuserIdは無視される(aws, repo, today):
    payload = {**POINTS_BODY, "userId": "attacker"}
    res = api_handler(make_event("POST /items", payload, sub=OTHER_SUB), None)
    assert body_of(res)["userId"] == OTHER_SUB


# ---------------------------------------------------------------- アップロードキー
def test_uploadsのキーは呼び出しユーザーのプレフィックスになる(aws, today):
    res = api_handler(
        make_event("POST /uploads", {"contentType": "image/png"}, sub=OTHER_SUB), None
    )
    assert body_of(res)["key"].startswith(f"uploads/{OTHER_SUB}/")


# ---------------------------------------------------------------- extract
def _put(key: str) -> None:
    boto3.client("s3", region_name="us-east-1").put_object(Bucket=BUCKET, Key=key, Body=PNG)


def test_extractは他ユーザーのS3キーを400で拒否し読まない(aws, today, make_bedrock):
    stub = make_bedrock([])
    key = f"uploads/{OTHER_SUB}/secret.png"
    _put(key)
    res = extract_handler(make_event("POST /extract", {"key": key}), None)
    assert res["statusCode"] == 400
    assert stub.calls == []


@pytest.mark.parametrize(
    "key_template",
    [
        "uploads/{me}/../{other}/x.png",
        "uploads/{other}/x.png",
        "uploads/{me}x/x.png",  # 前方一致のすり抜け（me + 追加文字）
        "uploads/{me}",  # スラッシュ無し
        "other/{me}/x.png",
    ],
)
def test_extractは自分のプレフィックス外のキーを拒否する(aws, today, make_bedrock, key_template):
    stub = make_bedrock([])
    key = key_template.format(me=DEFAULT_SUB, other=OTHER_SUB)
    res = extract_handler(make_event("POST /extract", {"key": key}), None)
    assert res["statusCode"] == 400
    assert stub.calls == []


def test_extractは自分のキーなら読み取りを実行する(aws, repo, today, make_bedrock):
    stub = make_bedrock(['{"service": "x", "lots": []}', "[]"])
    key = f"uploads/{OTHER_SUB}/mine.png"
    _put(key)
    res = extract_handler(make_event("POST /extract", {"key": key}, sub=OTHER_SUB), None)
    assert res["statusCode"] == 200
    assert len(stub.calls) >= 1


def test_extractが保存する下書きのuserIdは呼び出しユーザー(aws, repo, today, make_bedrock):
    reply = (
        '{"service": "PayPayポイント", "lots": '
        '[{"points": 114, "expiryDate": "2026-12-31", "isLimited": true}]}'
    )
    make_bedrock([reply])
    key = f"uploads/{OTHER_SUB}/mine.png"
    _put(key)
    res = extract_handler(make_event("POST /extract", {"key": key}, sub=OTHER_SUB), None)
    items = body_of(res)["items"]
    assert len(items) == 1
    assert items[0]["userId"] == OTHER_SUB
    assert repo.get(OTHER_SUB, items[0]["itemId"])["status"] == "draft"
    assert repo.get(DEFAULT_SUB, items[0]["itemId"]) is None


# ---------------------------------------------------------------- notify
def test_テスト通知は呼び出しユーザーの分だけ対象にする(aws, seed, today, ses_stub):
    seed(itemId="mine", service="MINE-SERVICE")
    seed(itemId="theirs", userId=OTHER_SUB, service="THEIRS-SERVICE")
    res = notify_handler(make_event("POST /notify/test"), None)
    assert body_of(res)["count"] == 1
    assert "MINE-SERVICE" in ses_stub.text()
    assert "THEIRS-SERVICE" not in ses_stub.text()


def test_テスト通知は自分のアイテムが無ければ他人分があってもサンプルになる(
    aws, seed, today, ses_stub
):
    seed(itemId="theirs", userId=OTHER_SUB, service="THEIRS-SERVICE")
    res = notify_handler(make_event("POST /notify/test"), None)
    assert body_of(res)["sample"] is True
    assert "THEIRS-SERVICE" not in ses_stub.text()


def test_日次通知は全ユーザー分を走査して通知しステージを各ユーザーに記録する(
    aws, repo, seed, today, ses_stub
):
    from datetime import timedelta

    due = (today + timedelta(days=7)).isoformat()
    seed(itemId="a1", service="A-SERVICE", expiryDate=due)
    seed(itemId="b1", userId=OTHER_SUB, service="B-SERVICE", expiryDate=due)
    result = notify_handler({"source": "aws.scheduler"}, None)
    assert result["notified"] == 2
    assert repo.get(DEFAULT_SUB, "a1")["lastNotifiedStage"] == "d7"
    assert repo.get(OTHER_SUB, "b1")["lastNotifiedStage"] == "d7"
    assert "A-SERVICE" in ses_stub.text()
    assert "B-SERVICE" in ses_stub.text()


# ---------------------------------------------------------------- repo.list_everyone
def test_scan_allは全ユーザーのアイテムを返す(aws, repo, seed, today):
    seed(itemId="a1")
    seed(itemId="b1", userId=OTHER_SUB)
    ids = {(i["userId"], i["itemId"]) for i in repo.scan_all()}
    assert ids == {(DEFAULT_SUB, "a1"), (OTHER_SUB, "b1")}


def test_scan_allは複数ページを読む(aws, repo):
    for n in range(3):
        repo.put({"userId": f"u{n}", "itemId": f"i{n}", "status": "active", "pad": "x" * 380000})
    assert len(repo.scan_all()) == 3
