"""notify Lambda: 日次の期限判定とメール送信、およびテスト通知。

- EventBridge Scheduler から起動 → 日次判定（ステージ管理で二重送信防止）
- POST /notify/test → 呼び出しユーザー分だけを対象に、ステージを無視して即時送信する
  （ステージ記録は更新しない）。日次判定は全ユーザー分を走査する
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from api.summary import at_risk_items, sort_by_expiry
from common import clients, dates
from common.auth import UnauthorizedError, user_id_from_event
from common.models import STATUS_ACTIVE
from common.repo import get_repository
from common.responses import error, respond
from notify.logic import advance_subscriptions, find_due, stage_name
from notify.mailer import DueItem, build_body, build_subject, send_mail

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TEST_ROUTE = "POST /notify/test"
MAX_TEST_ITEMS = 20  # テスト通知に載せる件数の上限
SAMPLE_DAYS = 7


def _risk_total(items: list[dict[str, Any]], today: Any) -> int:
    return sum(int(i.get("amount") or 0) for i in at_risk_items(items, today))


def _send(dues: list[DueItem], risk: int, *, is_test: bool, is_sample: bool = False) -> None:
    send_mail(
        clients.ses_client(),
        os.environ["SENDER_EMAIL"],
        os.environ["RECIPIENT_EMAIL"],
        build_subject(dues, is_test=is_test),
        build_body(dues, risk, os.environ.get("DASHBOARD_URL", ""), is_sample=is_sample),
    )


def _sample_item(today: Any) -> DueItem:
    expiry = (today + timedelta(days=SAMPLE_DAYS)).isoformat()
    item = {
        "kind": "points",
        "service": "PayPayポイント（サンプル）",
        "points": 114,
        "amount": 114,
        "expiryDate": expiry,
        "isLimited": True,
    }
    return DueItem(item=item, days=SAMPLE_DAYS)


def run_daily(today: Any) -> dict[str, Any]:
    """全ユーザー分を走査して判定する（宛先は SES サンドボックスのため RECIPIENT_EMAIL）。"""
    repo = get_repository()
    items, advanced = advance_subscriptions(repo, repo.scan_all(), today)
    dues = find_due(items, today)
    result = {"sent": False, "notified": 0, "failed": 0, "advanced": advanced}
    if not dues:
        return result
    try:
        _send(dues, _risk_total(items, today), is_test=False)
    except (ClientError, BotoCoreError):
        # 失敗は記録して継続。ステージは更新しないので翌日以降の再判定には影響しない
        logger.exception("ses send failed: %d items", len(dues))
        return {**result, "failed": len(dues)}
    for due in dues:
        repo.set_notified_stage(due.item["userId"], due.item["itemId"], stage_name(due.days))
    return {**result, "sent": True, "notified": len(dues)}


def run_test(user_id: str, today: Any) -> dict[str, Any]:
    """呼び出しユーザー自身のアイテムだけを対象にテスト通知を送る。"""
    items = get_repository().list_all(user_id)
    active = sort_by_expiry([i for i in items if i.get("status") == STATUS_ACTIVE])
    dues = [
        DueItem(item=i, days=dates.days_until(dates.parse_iso_date(i["expiryDate"]), today))
        for i in active[:MAX_TEST_ITEMS]
        if dates.parse_iso_date(i.get("expiryDate")) is not None
    ]
    is_sample = not dues
    if is_sample:
        dues = [_sample_item(today)]
    try:
        _send(dues, _risk_total(items, today), is_test=True, is_sample=is_sample)
    except (ClientError, BotoCoreError):
        logger.exception("test notification failed")
        return error(
            502, "メールを送信できませんでした。SES の送信元・宛先の認証を確認してください"
        )
    return respond(200, {"sent": True, "sample": is_sample, "count": len(dues)})


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    today = dates.jst_today()
    if event.get("routeKey") == TEST_ROUTE:
        try:
            return run_test(user_id_from_event(event), today)
        except UnauthorizedError as exc:
            return error(401, str(exc))
        except Exception:
            logger.exception("unexpected error")
            return error(500, "サーバーエラーが発生しました")
    return run_daily(today)
