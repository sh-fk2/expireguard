"""POST /uploads のテスト（要件 1.1, 1.3）。"""

import base64
import json

import pytest

from api.handler import lambda_handler
from conftest import BUCKET, body_of, make_event


def test_PNGで署名付きPOSTを返す(aws, today):
    res = lambda_handler(make_event("POST /uploads", {"contentType": "image/png"}), None)
    assert res["statusCode"] == 200
    body = body_of(res)
    assert body["key"].startswith("uploads/demo-user/")
    assert body["key"].endswith(".png")
    assert BUCKET in body["url"]
    assert body["fields"]["key"] == body["key"]


def test_署名付きPOSTはサイズと種別の条件を持つ(aws, today):
    res = lambda_handler(make_event("POST /uploads", {"contentType": "image/jpeg"}), None)
    body = body_of(res)
    assert body["key"].endswith(".jpg")
    policy = json.loads(base64.b64decode(body["fields"]["policy"]))
    flat = json.dumps(policy["conditions"])
    assert "content-length-range" in flat
    assert "image/jpeg" in flat
    assert body["maxBytes"] == 3_750_000


@pytest.mark.parametrize(
    "payload",
    [{"contentType": "application/pdf"}, {"contentType": "image/gif"}, {}, {"contentType": 5}],
)
def test_画像以外は400(aws, today, payload):
    res = lambda_handler(make_event("POST /uploads", payload), None)
    assert res["statusCode"] == 400
    assert "message" in body_of(res)
