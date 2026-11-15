"""notify Lambda のテスト（要件 8.1〜8.4, 9.1〜9.3, 10.1, 10.2）。"""

from datetime import timedelta

import pytest

from conftest import RECIPIENT, SENDER, SesRecorder, body_of, make_event
from notify.handler import lambda_handler


def _d(today, days):
    return (today + timedelta(days=days)).isoformat()


def _run():
    return lambda_handler({"source": "aws.scheduler"}, None)


def _sub(seed, today, days, **kw):
    return seed(
        kind="subscription",
        service="Netflix",
        amount=1590,
        cycle="monthly",
        points=None,
        isLimited=None,
        expiryDate=_d(today, days),
        **kw,
    )


@pytest.mark.parametrize("days", [30, 14, 7, 1])
def test_ポイントは30_14_7_1日前に通知する(aws, seed, today, ses_stub, days):
    seed(expiryDate=_d(today, days))
    result = _run()
    assert len(ses_stub.sent) == 1
    assert result["notified"] == 1


@pytest.mark.parametrize("days", [0, 2, 3, 6, 8, 15, 29, 31, -1])
def test_ポイントは対象外の日数では通知しない(aws, seed, today, ses_stub, days):
    seed(expiryDate=_d(today, days))
    assert _run()["notified"] == 0
    assert ses_stub.sent == []


@pytest.mark.parametrize("days", [7, 3, 1])
def test_サブスクは7_3_1日前に通知する(aws, seed, today, ses_stub, days):
    _sub(seed, today, days)
    assert _run()["notified"] == 1
    assert len(ses_stub.sent) == 1


@pytest.mark.parametrize("days", [30, 14, 5, 2])
def test_サブスクは対象外の日数では通知しない(aws, seed, today, ses_stub, days):
    _sub(seed, today, days)
    assert _run()["notified"] == 0


def test_有効以外のアイテムは通知しない(aws, seed, today, ses_stub):
    for status in ("draft", "used", "cancelled"):
        seed(expiryDate=_d(today, 7), status=status)
    assert _run()["notified"] == 0
    assert ses_stub.sent == []


def test_送信したステージを記録し同日の再実行で二重送信しない(aws, repo, seed, today, ses_stub):
    seed(itemId="p1", expiryDate=_d(today, 7))
    _run()
    assert repo.get("demo-user", "p1")["lastNotifiedStage"] == "d7"
    _run()
    assert len(ses_stub.sent) == 1


def test_別のステージになれば再び通知する(aws, repo, seed, today, ses_stub):
    seed(itemId="p1", expiryDate=_d(today, 1), lastNotifiedStage="d7")
    _run()
    assert len(ses_stub.sent) == 1
    assert repo.get("demo-user", "p1")["lastNotifiedStage"] == "d1"


def test_通知対象がなければメールを送らない(aws, seed, today, ses_stub):
    seed(expiryDate=_d(today, 100))
    result = _run()
    assert ses_stub.sent == []
    assert result["sent"] is False


def test_サービス名に期間限定が含まれていても本文で重複しない(aws, seed, today, ses_stub):
    # Nova がサービス名に「（期間限定）」を含めて返した保存データでも二重表記にしない
    seed(expiryDate=_d(today, 7), points=114, amount=114, service="PayPayポイント（期間限定）")
    _run()
    text = ses_stub.text()
    assert f"・PayPayポイント（期間限定）114pt — {_d(today, 7)} まで" in text
    assert "（期間限定）（期間限定）" not in text


def test_ポイント1件の件名と本文(aws, seed, today, ses_stub):
    seed(expiryDate=_d(today, 7), points=114, amount=114)
    seed(itemId="far", points=1000, amount=1000, expiryDate=_d(today, 20), service="楽天ポイント")
    _run()
    assert ses_stub.subject() == "PayPayポイント 114pt があと7日で切れます"
    text = ses_stub.text()
    assert f"・PayPayポイント（期間限定）114pt — {_d(today, 7)} まで（あと7日）" in text
    assert "失効リスク合計：1,114円分" in text  # 通知対象外でも30日以内なら合計に含める
    assert "https://dashboard.example.com" in text
    sent = ses_stub.sent[0]
    assert sent["FromEmailAddress"] == SENDER
    assert sent["Destination"] == {"ToAddresses": [RECIPIENT]}


def test_サブスク1件の件名と本文(aws, seed, today, ses_stub):
    _sub(seed, today, 3)
    _run()
    assert ses_stub.subject() == "Netflix 1,590円 の自動課金があと3日です"
    assert f"・Netflix 1,590円 — {_d(today, 3)} に自動更新（あと3日）" in ses_stub.text()


def test_複数件は1通にまとめる(aws, seed, today, ses_stub):
    seed(itemId="a", expiryDate=_d(today, 7))
    _sub(seed, today, 3)
    result = _run()
    assert len(ses_stub.sent) == 1
    assert result["notified"] == 2
    assert ses_stub.subject() == "ExpireGuard: 期限が近い項目が2件あります"


def test_SES失敗時はステージを更新せず処理を継続する(aws, repo, seed, today, monkeypatch):
    from common import clients

    monkeypatch.setattr(clients, "ses_client", lambda: SesRecorder(fail=True))
    seed(itemId="p1", expiryDate=_d(today, 7))
    result = _run()
    assert result["sent"] is False
    assert result["failed"] == 1
    assert "lastNotifiedStage" not in repo.get("demo-user", "p1")


def test_更新日を過ぎたサブスクは周期で繰り上げて保存する(aws, repo, seed, today, ses_stub):
    seed(
        itemId="s1",
        kind="subscription",
        amount=1590,
        cycle="monthly",
        service="Netflix",
        expiryDate="2026-10-20",
        lastNotifiedStage="d1",
    )
    seed(
        itemId="s2",
        kind="subscription",
        amount=12000,
        cycle="yearly",
        service="Prime",
        expiryDate="2026-03-01",
    )
    result = _run()
    assert result["advanced"] == 2
    s1 = repo.get("demo-user", "s1")
    assert s1["expiryDate"] == "2026-11-20"
    assert "lastNotifiedStage" not in s1  # 新しい周期ではステージをリセット
    assert repo.get("demo-user", "s2")["expiryDate"] == "2027-03-01"


def test_繰り上げ後の日付で通知判定する(aws, seed, today, ses_stub):
    # 2026-10-22 の月次 → 2026-11-22（7日後）に繰り上がり、同日中に通知される
    seed(
        kind="subscription",
        amount=1590,
        cycle="monthly",
        service="Netflix",
        expiryDate="2026-10-22",
    )
    assert _run()["notified"] == 1


def test_繰り上げ対象はactiveのサブスクだけ(aws, repo, seed, today, ses_stub):
    seed(
        itemId="c1",
        kind="subscription",
        amount=1,
        cycle="monthly",
        status="cancelled",
        expiryDate="2026-01-01",
    )
    seed(itemId="p1", expiryDate=_d(today, -5))
    result = _run()
    assert result["advanced"] == 0
    assert repo.get("demo-user", "c1")["expiryDate"] == "2026-01-01"
    assert repo.get("demo-user", "p1")["expiryDate"] == _d(today, -5)


def test_moto上の実SESクライアントでも送信できる(aws, seed, today):
    from moto.core import DEFAULT_ACCOUNT_ID
    from moto.ses import ses_backends

    seed(expiryDate=_d(today, 7))
    assert _run()["sent"] is True
    assert len(ses_backends[DEFAULT_ACCOUNT_ID]["us-east-1"].sent_messages) == 1


# ---- テスト通知（POST /notify/test） ----


def test_テスト通知は有効アイテムをもとに即時送信しステージを更新しない(
    aws, repo, seed, today, ses_stub
):
    seed(itemId="p1", expiryDate=_d(today, 20), lastNotifiedStage="d30")
    res = lambda_handler(make_event("POST /notify/test"), None)
    assert res["statusCode"] == 200
    assert body_of(res) == {"sent": True, "sample": False, "count": 1}
    assert ses_stub.subject().startswith("[テスト] ")
    assert "PayPayポイント" in ses_stub.text()
    assert repo.get("demo-user", "p1")["lastNotifiedStage"] == "d30"


def test_テスト通知は有効アイテムがなければサンプルで送信する(aws, today, ses_stub):
    res = lambda_handler(make_event("POST /notify/test"), None)
    assert body_of(res) == {"sent": True, "sample": True, "count": 1}
    assert "サンプル" in ses_stub.text()


def test_テスト通知は下書きや使用済みを含めない(aws, seed, today, ses_stub):
    seed(status="used")
    res = lambda_handler(make_event("POST /notify/test"), None)
    assert body_of(res)["sample"] is True


def test_テスト通知のSES失敗は502(aws, today, monkeypatch):
    from common import clients

    monkeypatch.setattr(clients, "ses_client", lambda: SesRecorder(fail=True))
    res = lambda_handler(make_event("POST /notify/test"), None)
    assert res["statusCode"] == 502
    assert "message" in body_of(res)


def test_ダッシュボードURL未設定ならリンク行を出さない(aws, seed, today, ses_stub, monkeypatch):
    monkeypatch.setenv("DASHBOARD_URL", "")
    seed(expiryDate=_d(today, 7))
    _run()
    assert "一覧はこちら" not in ses_stub.text()
