"""GET /summary の集計ロジック（要件 6.1〜6.5）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from common.dates import days_until, parse_iso_date
from common.models import (
    KIND_POINTS,
    KIND_SUBSCRIPTION,
    STATUS_ACTIVE,
    STATUS_CANCELLED,
    STATUS_USED,
)

RISK_WINDOW_DAYS = 30  # 失効リスクの対象期間


def sort_by_expiry(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """期限が近い順。日付なしは末尾。"""
    return sorted(items, key=lambda i: (i.get("expiryDate") is None, i.get("expiryDate") or ""))


def at_risk_items(items: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """30日以内に失効する有効なポイント（失効済みは含めない）。"""
    result = []
    for item in items:
        expiry = parse_iso_date(item.get("expiryDate"))
        if (
            item.get("status") == STATUS_ACTIVE
            and item.get("kind") == KIND_POINTS
            and expiry is not None
            and 0 <= days_until(expiry, today) <= RISK_WINDOW_DAYS
        ):
            result.append(item)
    return result


def build_summary(items: list[dict[str, Any]], today: date) -> dict[str, Any]:
    active = [i for i in items if i.get("status") == STATUS_ACTIVE]

    risk = at_risk_items(items, today)

    charge_amount = 0
    charge_count = 0
    for item in active:
        renewal = parse_iso_date(item.get("expiryDate"))
        if (
            item.get("kind") == KIND_SUBSCRIPTION
            and renewal is not None
            and (renewal.year, renewal.month) == (today.year, today.month)
        ):
            charge_amount += int(item.get("amount") or 0)
            charge_count += 1

    saved = sum(
        int(i.get("amount") or 0)
        for i in items
        if i.get("status") in (STATUS_USED, STATUS_CANCELLED)
    )

    listing = []
    for item in sort_by_expiry(active):
        expiry = parse_iso_date(item.get("expiryDate"))
        listing.append({**item, "daysLeft": days_until(expiry, today) if expiry else None})

    return {
        "atRiskAmount": sum(int(i.get("amount") or 0) for i in risk),
        "atRiskCount": len(risk),
        "upcomingCharges": {"amount": charge_amount, "count": charge_count},
        "savedAmount": saved,
        "items": listing,
    }
