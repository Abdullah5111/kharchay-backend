from decimal import Decimal
from apps.settlement.transfers import minimize_transfers


def test_simple_two_party():
    t = minimize_transfers({"a": Decimal("50.00"), "b": Decimal("-50.00")})
    assert t == [{"from": "a", "to": "b", "amount": Decimal("50.00")}]


def test_all_zero():
    assert minimize_transfers({"a": Decimal("0.00"), "b": Decimal("0.00")}) == []


def test_sum_conserved_three_party():
    nets = {"a": Decimal("100.00"), "b": Decimal("-40.00"), "c": Decimal("-60.00")}
    t = minimize_transfers(nets)
    assert sum(x["amount"] for x in t) == Decimal("100.00")
    # a is the only debtor -> at most 2 transfers
    assert all(x["from"] == "a" for x in t)
    assert len(t) <= 2


def test_no_self_or_zero_transfers():
    nets = {"a": Decimal("30.00"), "b": Decimal("-10.00"), "c": Decimal("-20.00")}
    t = minimize_transfers(nets)
    assert all(x["amount"] > 0 for x in t)
    assert all(x["from"] != x["to"] for x in t)
