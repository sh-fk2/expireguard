"""responses / repo の補助テスト。"""

import base64

import pytest

from common.responses import BadRequestError, parse_body, respond


def test_parse_bodyは空本文で空dictを返す():
    assert parse_body({"body": None}) == {}
    assert parse_body({"body": ""}) == {}


def test_parse_bodyは配列本文を拒否する():
    with pytest.raises(BadRequestError):
        parse_body({"body": "[1]"})


def test_parse_bodyは壊れたbase64を拒否する():
    with pytest.raises(BadRequestError):
        parse_body({"body": "!!!", "isBase64Encoded": True})
    bad_utf8 = base64.b64encode(b"\xff\xfe").decode()
    with pytest.raises(BadRequestError):
        parse_body({"body": bad_utf8, "isBase64Encoded": True})


def test_respondはDecimalを数値にする():
    from decimal import Decimal

    res = respond(200, {"a": Decimal("3"), "b": Decimal("1.5")})
    assert res["body"] == '{"a": 3, "b": 1.5}'


def test_respondは直列化できない型でTypeError():
    with pytest.raises(TypeError):
        respond(200, {"a": object()})


def test_list_allは複数ページを読む(aws, repo):
    for n in range(3):
        repo.put(
            {"userId": "demo-user", "itemId": f"i{n}", "status": "active", "pad": "x" * 380000}
        )
    assert len(repo.list_all("demo-user")) == 3
