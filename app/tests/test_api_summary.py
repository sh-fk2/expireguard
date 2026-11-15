"""GET /summary のテスト（要件 6.1〜6.5）。"""

from datetime import timedelta

from api.handler import lambda_handler
from conftest import body_of, make_event


def _summary():
    res = lambda_handler(make_event("GET /summary"), None)
    assert res["statusCode"] == 200
    return body_of(res)


def _d(today, days):
    return (today + timedelta(days=days)).isoformat()


def test_有効アイテムがなければ合計0(aws, today):
    s = _summary()
    assert s["atRiskAmount"] == 0
    assert s["atRiskCount"] == 0
    assert s["upcomingCharges"] == {"amount": 0, "count": 0}
    assert s["savedAmount"] == 0
    assert s["items"] == []


def test_失効リスクは30日以内のポイントだけ合計する(aws, seed, today):
    seed(points=100, amount=100, expiryDate=_d(today, 0))
    seed(points=200, amount=200, expiryDate=_d(today, 30))
    seed(points=400, amount=400, expiryDate=_d(today, 31))  # 範囲外
    seed(points=800, amount=800, expiryDate=_d(today, -1))  # 失効済み
    seed(kind="subscription", amount=1590, cycle="monthly", expiryDate=_d(today, 3))
    s = _summary()
    assert s["atRiskAmount"] == 300
    assert s["atRiskCount"] == 2


def test_自動課金予定は当月に更新日があるサブスクの合計(aws, seed, today):
    # 固定日は 2026-11-15。当月は 11/1〜11/30
    seed(kind="subscription", amount=1590, cycle="monthly", expiryDate="2026-11-20")
    seed(kind="subscription", amount=500, cycle="monthly", expiryDate="2026-11-01")
    seed(kind="subscription", amount=999, cycle="monthly", expiryDate="2026-12-01")
    s = _summary()
    assert s["upcomingCharges"] == {"amount": 2090, "count": 2}


def test_守れた金額は使用済みと解約済みの合計(aws, seed, today):
    seed(status="used", amount=114, points=114)
    seed(status="cancelled", kind="subscription", amount=1590, cycle="monthly")
    seed(status="draft", amount=9999, points=9999)
    seed(status="active", amount=50, points=50)
    assert _summary()["savedAmount"] == 114 + 1590


def test_一覧は有効のみ期限が近い順で残日数付き(aws, seed, today):
    seed(itemId="b", expiryDate=_d(today, 20))
    seed(itemId="a", expiryDate=_d(today, 2))
    seed(itemId="u", status="used")
    items = _summary()["items"]
    assert [i["itemId"] for i in items] == ["a", "b"]
    assert [i["daysLeft"] for i in items] == [2, 20]
