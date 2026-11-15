"""HTTP API (payload v2) 向けレスポンスと本文パース。"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from typing import Any

_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


class BadRequestError(Exception):
    """リクエスト本文が不正なとき。"""


def _default(value: Any) -> Any:
    """DynamoDB の Decimal を整数（または float）にする。"""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"unserializable: {type(value)}")


def respond(status: int, body: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"statusCode": status, "headers": dict(_HEADERS)}
    if body is not None:
        result["body"] = json.dumps(body, ensure_ascii=False, default=_default)
    return result


def error(status: int, message: str, **extra: Any) -> dict[str, Any]:
    """エラーは { "message": "..." } 形式で返す。"""
    return respond(status, {"message": message, **extra})


def parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """JSON オブジェクトの本文を読む。不正なら BadRequestError。"""
    raw = event.get("body")
    if raw is None or raw == "":
        return {}
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BadRequestError("リクエスト本文を読み取れません") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadRequestError("リクエスト本文が JSON ではありません") from exc
    if not isinstance(data, dict):
        raise BadRequestError("リクエスト本文は JSON オブジェクトにしてください")
    return data
