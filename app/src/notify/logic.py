"""日次判定ロジック（要件 8.1, 9.1, 9.3）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from common.dates import advance_renewal, days_until, parse_iso_date
from common.models import KIND_POINTS, KIND_SUBSCRIPTION, STATUS_ACTIVE
from common.repo import ItemRepository
from notify.mailer import DueItem

POINTS_STAGES = (30, 14, 7, 1)  # ポイントは失効の30・14・7・1日前
SUBSCRIPTION_STAGES = (7, 3, 1)  # サブスクは解約手続きの余裕を見て7・3・1日前
_STAGES = {KIND_POINTS: POINTS_STAGES, KIND_SUBSCRIPTION: SUBSCRIPTION_STAGES}


def stage_name(days: int) -> str:
    return f"d{days}"


def advance_subscriptions(
    repo: ItemRepository, items: list[dict[str, Any]], today: date
) -> tuple[list[dict[str, Any]], int]:
    """更新日を過ぎた有効サブスクを次の周期へ繰り上げて保存する。

    戻り値は (繰り上げ反映後の全アイテム, 繰り上げ件数)。
    """
    result = []
    advanced = 0
    for item in items:
        renewal = parse_iso_date(item.get("expiryDate"))
        if (
            item.get("status") == STATUS_ACTIVE
            and item.get("kind") == KIND_SUBSCRIPTION
            and renewal is not None
            and renewal < today
        ):
            new_date = advance_renewal(renewal, item["cycle"], today).isoformat()
            repo.set_renewal_date(item["userId"], item["itemId"], new_date)
            # 新しい周期では通知ステージをリセットする
            item = {k: v for k, v in item.items() if k != "lastNotifiedStage"}
            item["expiryDate"] = new_date
            advanced += 1
        result.append(item)
    return result, advanced


def find_due(items: list[dict[str, Any]], today: date) -> list[DueItem]:
    """今日が通知ステージに当たり、かつ同ステージを未送信の有効アイテム。"""
    due = []
    for item in items:
        if item.get("status") != STATUS_ACTIVE:
            continue
        expiry = parse_iso_date(item.get("expiryDate"))
        if expiry is None:
            continue
        days = days_until(expiry, today)
        if days in _STAGES.get(item.get("kind"), ()) and item.get(
            "lastNotifiedStage"
        ) != stage_name(days):
            due.append(DueItem(item=item, days=days))
    return due
