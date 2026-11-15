"""認証（JWT claims の sub）まわりのテスト。

HTTP API の JWT オーソライザーが検証済みの claims を渡す前提で、
Lambda 側の多層防御（sub 欠落の拒否）とユーザー分離を確認する。
"""

from __future__ import annotations

import pytest

from api.handler import lambda_handler as api_handler
from common.auth import UnauthorizedError, user_id_from_event
from conftest import DEFAULT_SUB, body_of, make_event
from extract.handler import lambda_handler as extract_handler
from notify.handler import lambda_handler as notify_handler

SUB_A = "11111111-aaaa-bbbb-cccc-000000000001"


def _claims_event(claims: object) -> dict:
    return {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}


# ---------------------------------------------------------------- user_id_from_event
def test_JWT_claimsのsubをユーザーIDとして返す():
    assert user_id_from_event(_claims_event({"sub": SUB_A})) == SUB_A


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"requestContext": None},
        {"requestContext": {}},
        {"requestContext": {"authorizer": None}},
        {"requestContext": {"authorizer": {}}},
        {"requestContext": {"authorizer": {"jwt": None}}},
        {"requestContext": {"authorizer": {"jwt": {}}}},
        _claims_event(None),
        _claims_event({}),
        _claims_event({"sub": ""}),
        _claims_event({"sub": None}),
        _claims_event({"sub": 123}),
        _claims_event({"sub": "a/b"}),
        _claims_event({"sub": "../x"}),
        _claims_event({"sub": "a b"}),
        _claims_event({"sub": "x" * 129}),
    ],
)
def test_subが無いか不正ならUnauthorizedError(event):
    with pytest.raises(UnauthorizedError):
        user_id_from_event(event)


def test_テスト用の既定ユーザーIDも受理される():
    assert user_id_from_event(make_event("GET /items")) == DEFAULT_SUB


# ---------------------------------------------------------------- sub 無しは拒否
_API_ROUTES = [
    ("GET /summary", None, None),
    ("GET /items", None, None),
    ("POST /items", {"kind": "points"}, None),
    ("PATCH /items/{id}", {"points": 1}, {"id": "x"}),
    ("DELETE /items/{id}", None, {"id": "x"}),
    ("POST /uploads", {"contentType": "image/png"}, None),
]


@pytest.mark.parametrize(("route", "body", "params"), _API_ROUTES)
def test_apiはsub無しを401で拒否する(aws, today, route, body, params):
    res = api_handler(make_event(route, body, params, sub=None), None)
    assert res["statusCode"] == 401
    assert "message" in body_of(res)


def test_extractはsub無しを401で拒否しBedrockを呼ばない(aws, today, make_bedrock):
    stub = make_bedrock([])
    event = make_event("POST /extract", {"key": f"uploads/{DEFAULT_SUB}/a.png"}, sub=None)
    res = extract_handler(event, None)
    assert res["statusCode"] == 401
    assert stub.calls == []


def test_notify_testはsub無しを401で拒否しメールを送らない(aws, seed, today, ses_stub):
    seed()
    res = notify_handler(make_event("POST /notify/test", sub=None), None)
    assert res["statusCode"] == 401
    assert ses_stub.sent == []


def test_401のレスポンスは内部情報を含まない(aws, today):
    res = api_handler(make_event("GET /items", sub=None), None)
    assert body_of(res) == {"message": "認証が必要です"}
