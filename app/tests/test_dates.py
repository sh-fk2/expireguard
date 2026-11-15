"""common.dates のテスト（要件 9.3 の日付繰り上げ、日付正規化の基礎）。"""

from datetime import date

import pytest

from common import dates


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-12-31", date(2026, 12, 31)),
        ("2026-02-30", None),
        ("2026-13-01", None),
        ("2026/12/31", None),
        ("", None),
        (None, None),
        (20261231, None),
    ],
)
def test_parse_iso_date_は不正な値でNoneを返す(value, expected):
    assert dates.parse_iso_date(value) == expected


def test_days_until_は残日数を返す():
    assert dates.days_until(date(2026, 11, 22), date(2026, 11, 15)) == 7
    assert dates.days_until(date(2026, 11, 14), date(2026, 11, 15)) == -1


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2027, 1, 31), 1, date(2027, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),
        (date(2026, 11, 20), 12, date(2027, 11, 20)),
    ],
)
def test_add_months_は月末を丸めて加算する(start, months, expected):
    assert dates.add_months(start, months) == expected


def test_advance_renewal_は未来の日付をそのまま返す():
    today = date(2026, 11, 15)
    assert dates.advance_renewal(date(2026, 11, 15), "monthly", today) == date(2026, 11, 15)
    assert dates.advance_renewal(date(2026, 11, 20), "monthly", today) == date(2026, 11, 20)


def test_advance_renewal_は月次で今日以降になるまで繰り上げる():
    today = date(2026, 11, 15)
    assert dates.advance_renewal(date(2026, 8, 20), "monthly", today) == date(2026, 11, 20)
    assert dates.advance_renewal(date(2026, 11, 14), "monthly", today) == date(2026, 12, 14)


def test_advance_renewal_は年次で繰り上げる():
    today = date(2026, 11, 15)
    assert dates.advance_renewal(date(2025, 3, 1), "yearly", today) == date(2027, 3, 1)


def test_advance_renewal_は未知の周期でValueError():
    with pytest.raises(ValueError, match="cycle"):
        dates.advance_renewal(date(2026, 1, 1), "weekly", date(2026, 11, 15))


def test_jst_today_はJSTの日付を返す():
    # UTC 15:00 は JST 翌日 0:00
    from datetime import UTC, datetime

    assert dates.jst_today(datetime(2026, 11, 14, 15, 0, tzinfo=UTC)) == date(2026, 11, 15)
    assert dates.jst_today(datetime(2026, 11, 14, 14, 59, tzinfo=UTC)) == date(2026, 11, 14)
