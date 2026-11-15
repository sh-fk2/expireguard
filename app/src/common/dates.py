"""日付ユーティリティ。「今日」は常に JST の日付で扱う。"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta

_JST = timedelta(hours=9)
_CYCLE_MONTHS = {"monthly": 1, "yearly": 12}


def jst_today(now: datetime | None = None) -> date:
    """JST の今日の日付を返す（テストでは now を渡して固定できる）。"""
    base = now or datetime.now(UTC)
    return (base.astimezone(UTC) + _JST).date()


def parse_iso_date(value: object) -> date | None:
    """YYYY-MM-DD 形式の文字列だけを日付に変換する。不正値は None。"""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def days_until(target: date, today: date) -> int:
    """today から target までの残日数（過去なら負）。"""
    return (target - today).days


def add_months(start: date, months: int) -> date:
    """月を加算する。移動先に同じ日がなければ月末に丸める。"""
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def advance_renewal(renewal: date, cycle: str, today: date) -> date:
    """更新日が今日より前なら、周期ごとに今日以降になるまで繰り上げる。"""
    if cycle not in _CYCLE_MONTHS:
        raise ValueError(f"unknown cycle: {cycle}")
    step = _CYCLE_MONTHS[cycle]
    count = 0
    result = renewal
    while result < today:
        count += 1
        # 元の日付を基準に加算し、月末丸めによるずれを1回の繰り上げ内では累積させない
        result = add_months(renewal, step * count)
    return result
