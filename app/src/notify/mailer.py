"""通知メールの組み立てと送信（設計書 §6 の文面）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.models import KIND_POINTS


@dataclass(frozen=True)
class DueItem:
    """通知対象の1件。days は期限（更新日）までの残日数。"""

    item: dict[str, Any]
    days: int


def _line(due: DueItem) -> str:
    item = due.item
    if item.get("kind") == KIND_POINTS:
        service = item["service"]
        # 保存済みのサービス名に「期間限定」が含まれていても二重に表記しない
        if item.get("isLimited") and "期間限定" not in service:
            label = f"{service}（期間限定）"
        else:
            label = f"{service} " if not item.get("isLimited") else service
        return f"・{label}{item['points']:,}pt — {item['expiryDate']} まで（あと{due.days}日）"
    return (
        f"・{item['service']} {item['amount']:,}円 — {item['expiryDate']} に自動更新"
        f"（あと{due.days}日）"
    )


def build_subject(dues: list[DueItem], *, is_test: bool = False) -> str:
    if len(dues) == 1:
        item, days = dues[0].item, dues[0].days
        if item.get("kind") == KIND_POINTS:
            subject = f"{item['service']} {item['points']:,}pt があと{days}日で切れます"
        else:
            subject = f"{item['service']} {item['amount']:,}円 の自動課金があと{days}日です"
    else:
        subject = f"ExpireGuard: 期限が近い項目が{len(dues)}件あります"
    return f"[テスト] {subject}" if is_test else subject


def build_body(
    dues: list[DueItem], risk_total: int, dashboard_url: str, *, is_sample: bool = False
) -> str:
    kinds = {d.item.get("kind") for d in dues}
    if kinds == {KIND_POINTS}:
        intro = "期限が近いポイントがあります。"
    elif KIND_POINTS not in kinds:
        intro = "自動更新が近いサブスクリプションがあります。"
    else:
        intro = "期限・更新が近い項目があります。"

    lines = [intro, ""]
    if is_sample:
        lines += ["※ 有効なアイテムがないため、サンプルの内容でお送りしています。", ""]
    lines += [_line(d) for d in dues]
    lines += ["", f"失効リスク合計：{risk_total:,}円分"]
    if dashboard_url:
        lines.append(f"一覧はこちら：{dashboard_url}")
    return "\n".join(lines) + "\n"


def send_mail(ses: Any, sender: str, recipient: str, subject: str, body: str) -> None:
    """SES v2 でテキストメールを送る。失敗時は ClientError がそのまま上がる。"""
    ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [recipient]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            }
        },
    )
