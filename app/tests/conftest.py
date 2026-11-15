"""テスト共通のフィクスチャ。AWS は moto でモックし、Bedrock と SES 送信はスタブにする。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import boto3
import pytest
from moto import mock_aws

# 実在しないテスト用アドレス（予約ドメイン example.com）
SENDER = "sender@example.com"
RECIPIENT = "recipient@example.com"
TABLE = "expireguard-items-test"
BUCKET = "expireguard-screenshots-test"
FIXED_TODAY = date(2026, 11, 15)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lambda の環境変数とダミー認証情報を設定する。"""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",  # noqa: S105
        "AWS_SESSION_TOKEN": "testing",  # noqa: S105
        "AWS_DEFAULT_REGION": "us-east-1",
        "TABLE_NAME": TABLE,
        "BUCKET_NAME": BUCKET,
        "BEDROCK_MODEL_ID": "us.anthropic.claude-sonnet-4-6",
        "SENDER_EMAIL": SENDER,
        "RECIPIENT_EMAIL": RECIPIENT,
        "DASHBOARD_URL": "https://dashboard.example.com",
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def aws():
    """DynamoDB テーブル・S3 バケット・SES 送信元を用意した moto 環境。"""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "itemId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "itemId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        ses = boto3.client("ses", region_name="us-east-1")
        ses.verify_email_identity(EmailAddress=SENDER)
        ses.verify_email_identity(EmailAddress=RECIPIENT)

        from common import clients

        clients.reset_caches()
        yield
        clients.reset_caches()


@pytest.fixture
def today(monkeypatch: pytest.MonkeyPatch) -> date:
    """「今日」を固定する（JST の日付）。"""
    from common import dates

    monkeypatch.setattr(dates, "jst_today", lambda: FIXED_TODAY)
    return FIXED_TODAY


@pytest.fixture
def repo(aws):
    from common.repo import get_repository

    return get_repository()


@pytest.fixture
def seed(repo, today):
    """アイテムを直接 DynamoDB に投入するヘルパー。"""
    counter = {"n": 0}

    def _seed(**overrides: Any) -> dict[str, Any]:
        counter["n"] += 1
        item: dict[str, Any] = {
            "userId": "demo-user",
            "itemId": f"item-{counter['n']}",
            "kind": "points",
            "service": "PayPayポイント",
            "points": 114,
            "amount": 114,
            "expiryDate": (today + timedelta(days=7)).isoformat(),
            "isLimited": True,
            "status": "active",
            "createdAt": "2026-11-01T00:00:00+00:00",
            "updatedAt": "2026-11-01T00:00:00+00:00",
        }
        item.update(overrides)
        repo.put(item)
        return item

    return _seed


DEFAULT_SUB = "demo-user"  # テストの既定ユーザー（JWT の sub 相当）。認証の有無とは無関係
OTHER_SUB = "other-user"


def make_event(
    route_key: str,
    body: Any = None,
    path_params: dict[str, str] | None = None,
    *,
    raw_body: str | None = None,
    base64_body: bool = False,
    sub: str | None = DEFAULT_SUB,
) -> dict[str, Any]:
    """HTTP API（payload v2）形式のイベントを作る。

    sub を渡すと JWT オーソライザー通過後の claims.sub を載せる。None なら認証情報なし。
    """
    text = raw_body if raw_body is not None else (None if body is None else json.dumps(body))
    if base64_body and text is not None:
        import base64

        text = base64.b64encode(text.encode()).decode()
    event: dict[str, Any] = {
        "routeKey": route_key,
        "pathParameters": path_params,
        "body": text,
        "isBase64Encoded": base64_body,
        "requestContext": {},
    }
    if sub is not None:
        event["requestContext"] = {"authorizer": {"jwt": {"claims": {"sub": sub}, "scopes": None}}}
    return event


def body_of(response: dict[str, Any]) -> Any:
    """レスポンスの body を JSON として読む。"""
    return json.loads(response["body"]) if response.get("body") else None


class SesRecorder:
    """SES 送信を記録するスタブ。fail=True で送信失敗を再現する。"""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail = fail

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail:
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "MessageRejected", "Message": "rejected"}}, "SendEmail"
            )
        self.sent.append(kwargs)
        return {"MessageId": "stub"}

    # 件名・本文を取り出す補助
    def subject(self, index: int = 0) -> str:
        return self.sent[index]["Content"]["Simple"]["Subject"]["Data"]

    def text(self, index: int = 0) -> str:
        return self.sent[index]["Content"]["Simple"]["Body"]["Text"]["Data"]


class BedrockStub:
    """Bedrock Runtime の converse を返却値キューで再現するスタブ。"""

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"output": {"message": {"content": [{"text": reply}]}}}


@pytest.fixture
def ses_stub(monkeypatch: pytest.MonkeyPatch, aws) -> SesRecorder:
    from common import clients

    recorder = SesRecorder()
    monkeypatch.setattr(clients, "ses_client", lambda: recorder)
    return recorder


@pytest.fixture
def make_bedrock(monkeypatch: pytest.MonkeyPatch, aws):
    from common import clients

    def _make(replies: list[Any]) -> BedrockStub:
        stub = BedrockStub(replies)
        monkeypatch.setattr(clients, "bedrock_client", lambda: stub)
        return stub

    return _make
