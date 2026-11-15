"""アイテムのデータモデルと入力検証（設計書 §3 / 要件 4.4, 5.4）。"""

from __future__ import annotations

from typing import Any

from common.dates import parse_iso_date

KIND_POINTS = "points"
KIND_SUBSCRIPTION = "subscription"
KINDS = (KIND_POINTS, KIND_SUBSCRIPTION)
CYCLES = ("monthly", "yearly")

STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_USED = "used"
STATUS_CANCELLED = "cancelled"

MAX_SERVICE_LENGTH = 100
MAX_NUMBER = 100_000_000  # ポイント数・金額の上限（入力ミス・桁あふれ対策）


class ValidationError(Exception):
    """入力検証エラー。fields に不足・不正な項目名を持つ。"""

    def __init__(self, message: str, fields: list[str]) -> None:
        super().__init__(message)
        self.message = message
        self.fields = fields


def coerce_positive_int(value: object, *, allow_text: bool = False) -> int | None:
    """正の整数に変換する。変換できない・範囲外は None。

    allow_text=True のとき "1,240" のような数字文字列も受け付ける（抽出結果用）。
    """
    if isinstance(value, bool):
        return None
    number: int | None = None
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    elif allow_text and isinstance(value, str):
        digits = value.replace(",", "").strip()
        number = int(digits) if digits.isdigit() else None
    if number is None or number < 1 or number > MAX_NUMBER:
        return None
    return number


def clean_service(value: object) -> str | None:
    """サービス名を整形する。空・長すぎる値は None。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > MAX_SERVICE_LENGTH:
        return None
    return text


def validate_item_fields(data: dict[str, Any]) -> dict[str, Any]:
    """確定登録用に項目を検証し、保存する項目だけの dict を返す。"""
    if not isinstance(data, dict):
        raise ValidationError("入力が不正です", ["body"])

    bad: list[str] = []
    kind = data.get("kind", KIND_POINTS)
    if kind not in KINDS:
        raise ValidationError("kind が不正です", ["kind"])

    service = clean_service(data.get("service"))
    if service is None:
        bad.append("service")
    expiry = parse_iso_date(data.get("expiryDate"))
    if expiry is None:
        bad.append("expiryDate")

    out: dict[str, Any] = {"kind": kind, "service": service, "expiryDate": data.get("expiryDate")}
    if kind == KIND_POINTS:
        points = coerce_positive_int(data.get("points"))
        if points is None:
            bad.append("points")
        out.update(points=points, amount=points, isLimited=bool(data.get("isLimited", False)))
    else:
        amount = coerce_positive_int(data.get("amount"))
        if amount is None:
            bad.append("amount")
        cycle = data.get("cycle")
        if cycle not in CYCLES:
            bad.append("cycle")
        out.update(amount=amount, cycle=cycle)

    if bad:
        raise ValidationError("入力に不足または不正な項目があります: " + ", ".join(bad), bad)
    return out
