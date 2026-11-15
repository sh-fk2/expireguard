"""Bedrock 応答の JSON 解釈と、抽出結果の正規化（要件 2.1〜2.5, 3.1〜3.4）。"""

from __future__ import annotations

import json
import re
from typing import Any

from common.dates import parse_iso_date
from common.models import CYCLES, clean_service, coerce_positive_int


def parse_model_json(text: str) -> Any | None:
    """応答テキストから JSON を取り出す。失敗したら None。

    そのまま読めなければ、最初の { または [ から最後の } または ] までを切り出して再パースする。
    """
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (stripped.find("{"), stripped.find("[")) if i != -1]
    end = max(stripped.rfind("}"), stripped.rfind("]"))
    if not starts or end <= min(starts):
        return None
    try:
        return json.loads(stripped[min(starts) : end + 1])
    except json.JSONDecodeError:
        return None


def _valid_date(value: object) -> str | None:
    """正しい YYYY-MM-DD のみ残す。不正な日付は推測せず None。"""
    return value if parse_iso_date(value) is not None else None  # type: ignore[return-value]


def _strip_limited_suffix(service: str | None) -> str | None:
    """サービス名末尾の「（期間限定）」を取り除く。期間限定かどうかは isLimited で表すため。"""
    if service is None:
        return None
    stripped = re.sub(r"\s*[（(]\s*期間限定\s*[）)]\s*$", "", service).strip()
    return stripped or service


def normalize_points(data: Any) -> list[dict[str, Any]]:
    """ポイント用の抽出結果を、ロットごとの項目 dict に直す。読めないロットは除く。"""
    if not isinstance(data, dict) or not isinstance(data.get("lots"), list):
        return []
    service = _strip_limited_suffix(clean_service(data.get("service")))
    lots = []
    for lot in data["lots"]:
        if not isinstance(lot, dict):
            continue
        points = coerce_positive_int(lot.get("points"), allow_text=True)
        if points is None:
            continue
        flag = lot.get("isLimited")
        lots.append(
            {
                "kind": "points",
                "service": service,
                "points": points,
                "amount": points,  # 1pt = 1円
                "expiryDate": _valid_date(lot.get("expiryDate")),
                "isLimited": flag is True or (isinstance(flag, str) and flag.lower() == "true"),
            }
        )
    return lots


def normalize_subscriptions(data: Any) -> list[dict[str, Any]]:
    """サブスク用の抽出結果（単一オブジェクトまたは配列）を項目 dict の一覧に直す。"""
    entries = data if isinstance(data, list) else [data]
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        service = clean_service(entry.get("service"))
        amount = coerce_positive_int(entry.get("amount"), allow_text=True)
        if service is None and amount is None:
            continue
        # トライアル終了日は課金開始日として次回更新日より優先する
        expiry = _valid_date(entry.get("trialEndDate")) or _valid_date(entry.get("nextRenewalDate"))
        cycle = entry.get("cycle")
        result.append(
            {
                "kind": "subscription",
                "service": service,
                "amount": amount,
                "expiryDate": expiry,
                "cycle": cycle if cycle in CYCLES else None,
            }
        )
    return result
