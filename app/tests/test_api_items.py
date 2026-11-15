"""api Lambda の items CRUD テスト（要件 4.2, 5.4, 7.1〜7.4）。"""

from datetime import timedelta

from api.handler import lambda_handler
from conftest import body_of, make_event

POINTS_BODY = {
    "kind": "points",
    "service": "楽天ポイント",
    "points": 1240,
    "expiryDate": "2026-11-30",
    "isLimited": True,
}
SUB_BODY = {
    "kind": "subscription",
    "service": "Netflix",
    "amount": 1590,
    "cycle": "monthly",
    "expiryDate": "2026-11-20",
}


def test_POST_itemsはactiveで保存し201を返す(aws, repo, today):
    res = lambda_handler(make_event("POST /items", POINTS_BODY), None)
    assert res["statusCode"] == 201
    item = body_of(res)
    assert item["status"] == "active"
    assert item["userId"] == "demo-user"
    assert item["amount"] == 1240
    assert repo.get("demo-user", item["itemId"])["service"] == "楽天ポイント"


def test_POST_itemsは必須欠落で400と不足項目を返す(aws, today):
    res = lambda_handler(make_event("POST /items", {"kind": "points"}), None)
    assert res["statusCode"] == 400
    body = body_of(res)
    assert {"service", "expiryDate", "points"} <= set(body["fields"])
    assert body["message"]


def test_POST_itemsは壊れたJSONで400(aws, today):
    res = lambda_handler(make_event("POST /items", raw_body="{oops"), None)
    assert res["statusCode"] == 400


def test_POST_itemsはbase64本文も読める(aws, today):
    res = lambda_handler(make_event("POST /items", POINTS_BODY, base64_body=True), None)
    assert res["statusCode"] == 201


def test_POST_itemsはdraftIdで下書きを確定する(aws, repo, seed, today):
    seed(itemId="d1", status="draft", ttl=1900000000, service="読み違い")
    res = lambda_handler(make_event("POST /items", {**POINTS_BODY, "draftId": "d1"}), None)
    assert res["statusCode"] == 201
    stored = repo.get("demo-user", "d1")
    assert stored["status"] == "active"
    assert stored["service"] == "楽天ポイント"
    assert "ttl" not in stored


def test_POST_itemsは下書き以外のdraftIdを404にする(aws, seed, today):
    seed(itemId="a1", status="active")
    res = lambda_handler(make_event("POST /items", {**POINTS_BODY, "draftId": "a1"}), None)
    assert res["statusCode"] == 404
    res = lambda_handler(make_event("POST /items", {**POINTS_BODY, "draftId": "none"}), None)
    assert res["statusCode"] == 404


def test_GET_itemsは下書きを除いて期限順に返す(aws, seed, today):
    seed(itemId="late", expiryDate=(today + timedelta(days=30)).isoformat())
    seed(itemId="soon", expiryDate=(today + timedelta(days=1)).isoformat())
    seed(itemId="draft", status="draft")
    res = lambda_handler(make_event("GET /items"), None)
    ids = [i["itemId"] for i in body_of(res)["items"]]
    assert ids == ["soon", "late"]


def test_PATCH_itemsは内容を更新し日付変更で通知ステージを消す(aws, repo, seed, today):
    seed(itemId="p1", lastNotifiedStage="d7")
    res = lambda_handler(
        make_event("PATCH /items/{id}", {"points": 200, "expiryDate": "2026-12-01"}, {"id": "p1"}),
        None,
    )
    assert res["statusCode"] == 200
    stored = repo.get("demo-user", "p1")
    assert stored["points"] == 200
    assert stored["amount"] == 200
    assert stored["expiryDate"] == "2026-12-01"
    assert "lastNotifiedStage" not in stored


def test_PATCH_itemsは日付が同じなら通知ステージを残す(aws, repo, seed, today):
    item = seed(itemId="p1", lastNotifiedStage="d7")
    lambda_handler(make_event("PATCH /items/{id}", {"service": "PayPay"}, {"id": "p1"}), None)
    stored = repo.get("demo-user", "p1")
    assert stored["lastNotifiedStage"] == "d7"
    assert stored["expiryDate"] == item["expiryDate"]


def test_PATCH_itemsは不正値を400にする(aws, seed, today):
    seed(itemId="p1")
    res = lambda_handler(make_event("PATCH /items/{id}", {"expiryDate": "bad"}, {"id": "p1"}), None)
    assert res["statusCode"] == 400


def test_PATCH_itemsのstatususedでポイントを使用済みにする(aws, repo, seed, today):
    seed(itemId="p1")
    res = lambda_handler(make_event("PATCH /items/{id}", {"status": "used"}, {"id": "p1"}), None)
    assert res["statusCode"] == 200
    assert repo.get("demo-user", "p1")["status"] == "used"


def test_PATCH_itemsのstatuscancelledでサブスクを解約済みにする(aws, repo, seed, today):
    seed(
        itemId="s1",
        kind="subscription",
        amount=1590,
        cycle="monthly",
        service="Netflix",
        expiryDate="2026-11-20",
    )
    res = lambda_handler(
        make_event("PATCH /items/{id}", {"status": "cancelled"}, {"id": "s1"}), None
    )
    assert res["statusCode"] == 200
    assert repo.get("demo-user", "s1")["status"] == "cancelled"


def test_PATCH_itemsは種別に合わないstatusを400にする(aws, seed, today):
    seed(itemId="p1")
    res = lambda_handler(
        make_event("PATCH /items/{id}", {"status": "cancelled"}, {"id": "p1"}), None
    )
    assert res["statusCode"] == 400
    res = lambda_handler(make_event("PATCH /items/{id}", {"status": "draft"}, {"id": "p1"}), None)
    assert res["statusCode"] == 400


def test_PATCH_itemsはactive以外を409にする(aws, seed, today):
    seed(itemId="p1", status="used")
    res = lambda_handler(make_event("PATCH /items/{id}", {"points": 1}, {"id": "p1"}), None)
    assert res["statusCode"] == 409


def test_PATCH_itemsは存在しないIDを404にする(aws, today):
    res = lambda_handler(make_event("PATCH /items/{id}", {"points": 1}, {"id": "nope"}), None)
    assert res["statusCode"] == 404


def test_DELETE_itemsは削除して204を返す(aws, repo, seed, today):
    seed(itemId="p1")
    res = lambda_handler(make_event("DELETE /items/{id}", None, {"id": "p1"}), None)
    assert res["statusCode"] == 204
    assert repo.get("demo-user", "p1") is None
    res = lambda_handler(make_event("DELETE /items/{id}", None, {"id": "p1"}), None)
    assert res["statusCode"] == 404


def test_未知のルートは404(aws, today):
    res = lambda_handler(make_event("GET /unknown"), None)
    assert res["statusCode"] == 404
    assert "message" in body_of(res)


def test_サブスクの新規登録(aws, today):
    res = lambda_handler(make_event("POST /items", SUB_BODY), None)
    assert res["statusCode"] == 201
    assert body_of(res)["cycle"] == "monthly"


def test_想定外の例外は500でmessageだけ返す(aws, today, monkeypatch):
    import api.handler as handler

    def boom(*_a, **_k):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(handler, "get_repository", boom)
    res = lambda_handler(make_event("GET /items"), None)
    assert res["statusCode"] == 500
    assert "secret detail" not in res["body"]
