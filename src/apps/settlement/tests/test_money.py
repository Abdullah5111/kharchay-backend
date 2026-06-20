from decimal import Decimal
import pytest
from apps.settlement.money import quantize, apportion


def test_quantize_half_up():
    assert quantize(Decimal("1.005")) == Decimal("1.01")


def test_apportion_sums_exactly():
    parts = apportion(Decimal("100.00"), [Decimal(1), Decimal(1), Decimal(1)])
    assert sum(parts) == Decimal("100.00")
    assert parts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_apportion_weighted():
    parts = apportion(Decimal("90.00"), [Decimal(1), Decimal(2)])
    assert sum(parts) == Decimal("90.00")
    assert parts == [Decimal("30.00"), Decimal("60.00")]


def test_apportion_remainder_to_last_nonzero():
    parts = apportion(Decimal("10.00"), [Decimal(1), Decimal(0), Decimal(1), Decimal(1)])
    assert parts[1] == Decimal("0.00")
    assert sum(parts) == Decimal("10.00")


def test_apportion_zero_total():
    assert apportion(Decimal("0.00"), [Decimal(1), Decimal(1)]) == [Decimal("0.00"), Decimal("0.00")]


def test_apportion_all_zero_weights():
    assert apportion(Decimal("10.00"), [Decimal(0), Decimal(0)]) == [Decimal("0.00"), Decimal("0.00")]
