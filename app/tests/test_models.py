"""common.models の入力検証テスト（要件 4.4, 5.4）。"""

import pytest

from common.models import ValidationError, validate_item_fields


def _points(**kw):
    base = {
        "kind": "points",
        "service": "PayPayポイント",
        "points": 114,
        "expiryDate": "2026-12-31",
        "isLimited": True,
    }
    base.update(kw)
    return base


def test_ポイントの正常入力はamountにpointsを写す():
    out = validate_item_fields(_points())
    assert out["points"] == 114
    assert out["amount"] == 114
    assert out["isLimited"] is True
    assert "cycle" not in out


def test_kind省略時はpointsとして扱う():
    data = _points()
    del data["kind"]
    assert validate_item_fields(data)["kind"] == "points"


def test_isLimited省略時はFalse():
    data = _points()
    del data["isLimited"]
    assert validate_item_fields(data)["isLimited"] is False


@pytest.mark.parametrize("missing", ["service", "expiryDate", "points"])
def test_必須項目が欠けると不足項目名を返す(missing):
    data = _points()
    del data[missing]
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(data)
    assert missing in exc.value.fields


def test_空白だけのサービス名は不足扱い():
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(_points(service="   "))
    assert exc.value.fields == ["service"]


@pytest.mark.parametrize("bad", ["2026-02-30", "12/31", None, 5])
def test_不正な日付はexpiryDateエラー(bad):
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(_points(expiryDate=bad))
    assert "expiryDate" in exc.value.fields


@pytest.mark.parametrize("bad", [0, -1, True, "abc", 1.5, 10**9])
def test_不正なポイント数はpointsエラー(bad):
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(_points(points=bad))
    assert "points" in exc.value.fields


def test_整数値のfloatは受け付ける():
    assert validate_item_fields(_points(points=114.0))["points"] == 114


def test_サブスクは金額と周期が必須():
    data = {"kind": "subscription", "service": "Netflix", "expiryDate": "2026-11-20"}
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(data)
    assert set(exc.value.fields) == {"amount", "cycle"}


def test_サブスクの正常入力はpointsとisLimitedを持たない():
    out = validate_item_fields(
        {
            "kind": "subscription",
            "service": "Netflix",
            "amount": 1590,
            "cycle": "monthly",
            "expiryDate": "2026-11-20",
        }
    )
    assert out["amount"] == 1590
    assert out["cycle"] == "monthly"
    assert "points" not in out
    assert "isLimited" not in out


def test_不正なkindはkindエラー():
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(_points(kind="coupon"))
    assert "kind" in exc.value.fields


def test_不正な周期はcycleエラー():
    with pytest.raises(ValidationError) as exc:
        validate_item_fields(
            {
                "kind": "subscription",
                "service": "X",
                "amount": 1,
                "cycle": "weekly",
                "expiryDate": "2026-11-20",
            }
        )
    assert "cycle" in exc.value.fields


def test_サービス名が長すぎるとエラー():
    with pytest.raises(ValidationError):
        validate_item_fields(_points(service="a" * 101))


def test_dictでない入力はエラー():
    with pytest.raises(ValidationError):
        validate_item_fields("x")  # type: ignore[arg-type]
