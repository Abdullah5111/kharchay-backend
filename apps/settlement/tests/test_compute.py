from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Expense, ExpenseShare
from apps.haazri.models import MealEvent, MealAttendance, ExtraAmount
from apps.settlement.compute import compute_settlement

User = get_user_model()


def make_group(owner, *members):
    g = Group.objects.create(name="House 8", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def cat(g, kind, name):
    return Category.objects.create(group=g, ledger_type=kind, name=name)


def expense(g, ledger, category, amount, paid_by, date="2026-06-05", shares=None, split="equal"):
    e = Expense.objects.create(
        group=g, ledger_type=ledger, category=category, amount=Decimal(amount),
        paid_by=paid_by, date=date, split_type=("" if ledger == "kitchen" else split),
        created_by=paid_by,
    )
    for u, amt in (shares or {}).items():
        ExpenseShare.objects.create(expense=e, user=u, amount=Decimal(amt))
    return e


def meal(g, pool, date, attendees):
    """attendees: dict user -> multiplier."""
    ev = MealEvent.objects.create(group=g, category=pool, date=date, created_by=g.owner)
    for u, mult in attendees.items():
        MealAttendance.objects.create(meal_event=ev, user=u, multiplier=mult)
    return ev


def users(*names):
    return [User.objects.create_user(email=f"{n}@e.com", name=n.upper()) for n in names]


def assert_balanced(result):
    assert sum(l["net"] for l in result["lines"].values()) == Decimal("0.00")


@pytest.mark.django_db
def test_equal_nonkitchen_two_members():
    a, b = users("a", "b")
    g = make_group(a, b)
    rent = cat(g, "monthly_expense", "Rent")
    expense(g, "monthly_expense", rent, "100.00", a, shares={a: "50.00", b: "50.00"})
    r = compute_settlement(g, 2026, 6)
    assert r["lines"][a.id]["net"] == Decimal("-50.00")   # owed 50, paid 100
    assert r["lines"][b.id]["net"] == Decimal("50.00")    # owed 50, paid 0
    assert_balanced(r)


@pytest.mark.django_db
def test_custom_split_nonkitchen():
    a, b = users("a", "b")
    g = make_group(a, b)
    food = cat(g, "monthly_expense", "Bills")
    expense(g, "monthly_expense", food, "100.00", b, shares={a: "70.00", b: "30.00"}, split="custom")
    r = compute_settlement(g, 2026, 6)
    assert r["lines"][a.id]["net"] == Decimal("70.00")
    assert r["lines"][b.id]["net"] == Decimal("-70.00")
    assert_balanced(r)


@pytest.mark.django_db
def test_kitchen_pool_rate_by_units():
    a, b = users("a", "b")
    g = make_group(a, b)
    lunch = cat(g, "kitchen_pool", "Lunch")
    expense(g, "kitchen", lunch, "300.00", a)            # a fronts 300 of groceries
    meal(g, lunch, "2026-06-01", {a: 1, b: 2})           # total units 3, rate 100
    r = compute_settlement(g, 2026, 6)
    assert r["lines"][a.id]["net"] == Decimal("-200.00")  # owed 100, paid 300
    assert r["lines"][b.id]["net"] == Decimal("200.00")   # owed 200, paid 0
    assert_balanced(r)


@pytest.mark.django_db
def test_kitchen_zero_units_no_divide_by_zero():
    a, = users("a")
    g = make_group(a)
    lunch = cat(g, "kitchen_pool", "Lunch")
    expense(g, "kitchen", lunch, "300.00", a)            # spend but NO attendance
    r = compute_settlement(g, 2026, 6)                   # must NOT raise
    assert r["lines"][a.id]["net"] == Decimal("-300.00")  # unallocated; payer left owed
    # deliberately NOT balanced — see Global Constraints zero-units note


@pytest.mark.django_db
def test_extra_weighted_by_multiplier():
    a, b = users("a", "b")
    g = make_group(a, b)
    lunch = cat(g, "kitchen_pool", "Lunch")
    ev = meal(g, lunch, "2026-06-05", {a: 1, b: 2})
    ExtraAmount.objects.create(meal_event=ev, title="juice", amount=Decimal("30.00"), paid_by=a, created_by=a)
    r = compute_settlement(g, 2026, 6)
    assert r["lines"][a.id]["net"] == Decimal("-20.00")   # extra share 10, paid 30
    assert r["lines"][b.id]["net"] == Decimal("20.00")    # extra share 20
    assert_balanced(r)


@pytest.mark.django_db
def test_rounding_remainder_keeps_balance():
    a, b, c = users("a", "b", "c")
    g = make_group(a, b, c)
    lunch = cat(g, "kitchen_pool", "Lunch")
    expense(g, "kitchen", lunch, "100.00", a)
    meal(g, lunch, "2026-06-01", {a: 1, b: 1, c: 1})      # 33.33/33.33/33.34
    r = compute_settlement(g, 2026, 6)
    owed = [r["lines"][u.id]["owed_total"] for u in (a, b, c)]
    assert sum(owed) == Decimal("100.00")
    assert_balanced(r)


@pytest.mark.django_db
def test_only_target_month_counted():
    a, b = users("a", "b")
    g = make_group(a, b)
    rent = cat(g, "monthly_expense", "Rent")
    expense(g, "monthly_expense", rent, "100.00", a, date="2026-05-30", shares={a: "50.00", b: "50.00"})
    r = compute_settlement(g, 2026, 6)
    assert r["lines"] == {}   # the May expense is excluded from June


@pytest.mark.django_db
def test_empty_month_no_participants():
    a, = users("a")
    g = make_group(a)
    r = compute_settlement(g, 2026, 6)
    assert r["lines"] == {}
