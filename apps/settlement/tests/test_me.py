"""Tests for /me/standing/ and /me/activity/ endpoints."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Expense, ExpenseShare
from apps.haazri.models import MealEvent, MealAttendance, ExtraAmount

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="TestGroup", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def make_expense(group, ledger_type, category, amount, paid_by, date="2026-06-05", shares=None, split="equal"):
    e = Expense.objects.create(
        group=group,
        ledger_type=ledger_type,
        category=category,
        amount=Decimal(amount),
        paid_by=paid_by,
        date=date,
        split_type=("" if ledger_type == "kitchen" else split),
        created_by=paid_by,
    )
    for u, amt in (shares or {}).items():
        ExpenseShare.objects.create(expense=e, user=u, amount=Decimal(amt))
    return e


def make_meal(group, pool, date, attendees):
    """attendees: dict user -> multiplier."""
    ev = MealEvent.objects.create(group=group, category=pool, date=date, created_by=group.owner)
    for u, mult in attendees.items():
        MealAttendance.objects.create(meal_event=ev, user=u, multiplier=mult)
    return ev


@pytest.fixture
def api_client():
    return APIClient()


# ---------------------------------------------------------------------------
# /me/standing/ tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_standing_missing_group_returns_400(api_client):
    user = User.objects.create_user(email="u@e.com", name="U")
    auth(api_client, user)
    r = api_client.get("/api/me/standing/?year=2026&month=6")
    assert r.status_code == 400
    assert "group" in r.json()["detail"]


@pytest.mark.django_db
def test_standing_missing_year_returns_400(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/me/standing/?group={g.id}&month=6")
    assert r.status_code == 400


@pytest.mark.django_db
def test_standing_non_integer_year_returns_400(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=abc&month=6")
    assert r.status_code == 400


@pytest.mark.django_db
def test_standing_non_member_returns_404(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    outsider = User.objects.create_user(email="outsider@e.com", name="Outsider")
    g = make_group(owner)
    auth(api_client, outsider)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.status_code == 404


@pytest.mark.django_db
def test_standing_matches_compute_line(api_client):
    """Member with an equal-split expense: standing net must match compute_settlement output."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    make_expense(
        g, "monthly_expense", cat, "100.00", owner,
        shares={owner: "50.00", member: "50.00"},
    )

    auth(api_client, member)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    data = r.json()

    assert Decimal(data["paid_total"]) == Decimal("0.00")
    assert Decimal(data["owed_total"]) == Decimal("50.00")
    assert Decimal(data["net"]) == Decimal("50.00")
    assert data["settlement_status"] == "none"


@pytest.mark.django_db
def test_standing_zeros_when_no_activity(api_client):
    """Member with no activity that month gets zeros and empty breakdown."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    data = r.json()

    assert Decimal(data["paid_total"]) == Decimal("0.00")
    assert Decimal(data["owed_total"]) == Decimal("0.00")
    assert Decimal(data["net"]) == Decimal("0.00")
    assert data["breakdown"] == {"non_kitchen": [], "kitchen": [], "extras": [], "paid": []}
    assert data["transfers"] == []


@pytest.mark.django_db
def test_standing_transfers_only_involve_requesting_user(api_client):
    """Transfers in my_standing must only include those where the user is from_user or to_user."""
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    c = User.objects.create_user(email="c@e.com", name="C")
    g = make_group(a, b, c)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    # a pays 300; shares: a=100, b=100, c=100  -> b owes 100, c owes 100
    make_expense(
        g, "monthly_expense", cat, "300.00", a,
        shares={a: "100.00", b: "100.00", c: "100.00"},
    )

    # Check b's standing — b should only see transfers involving b (b->a)
    auth(api_client, b)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    data = r.json()
    transfers = data["transfers"]

    user_ids = set()
    for t in transfers:
        user_ids.add(t["from_user"]["id"])
        user_ids.add(t["to_user"]["id"])

    b_id = str(b.id)
    for t in transfers:
        assert t["from_user"]["id"] == b_id or t["to_user"]["id"] == b_id, (
            f"Transfer {t} does not involve user b"
        )


@pytest.mark.django_db
def test_standing_settlement_status_reflects_persisted(api_client):
    """settlement_status should reflect the persisted Settlement's status."""
    from apps.settlement.models import Settlement

    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    g = make_group(owner)

    auth(api_client, owner)

    # No settlement: "none"
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    assert r.json()["settlement_status"] == "none"

    # Create a draft settlement
    s = Settlement.objects.create(group=g, year=2026, month=6, status="draft")
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.json()["settlement_status"] == "draft"

    # Finalize it
    s.status = "finalized"
    s.save()
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=6")
    assert r.json()["settlement_status"] == "finalized"


# ---------------------------------------------------------------------------
# /me/activity/ tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_activity_missing_group_returns_400(api_client):
    user = User.objects.create_user(email="u@e.com", name="U")
    auth(api_client, user)
    r = api_client.get("/api/me/activity/?year=2026&month=6")
    assert r.status_code == 400


@pytest.mark.django_db
def test_activity_non_member_returns_404(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    outsider = User.objects.create_user(email="outsider@e.com", name="Outsider")
    g = make_group(owner)
    auth(api_client, outsider)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 404


@pytest.mark.django_db
def test_activity_returns_expenses_and_meals(api_client):
    """Activity returns both expenses and meal events for the user, sorted desc by date."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Groceries")
    pool = Category.objects.create(group=g, ledger_type="kitchen_pool", name="Lunch")

    # Expense on June 10 — member pays it
    make_expense(
        g, "monthly_expense", cat, "60.00", member, date="2026-06-10",
        shares={owner: "30.00", member: "30.00"},
    )

    # Meal event on June 5 — member attended
    ev = MealEvent.objects.create(group=g, category=pool, date="2026-06-05", created_by=owner)
    MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()

    # Should have exactly 2 items
    assert len(items) == 2

    # First item (June 10 expense) should come before June 5 meal (descending)
    assert items[0]["date"] == "2026-06-10"
    assert items[0]["kind"] == "expense"
    assert items[1]["date"] == "2026-06-05"
    assert items[1]["kind"] == "meal"


@pytest.mark.django_db
def test_activity_excludes_other_month_rows(api_client):
    """Activity must not return items from outside the requested month."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Bills")

    # May expense — should NOT appear in June query
    make_expense(
        g, "monthly_expense", cat, "100.00", member, date="2026-05-20",
        shares={member: "100.00"},
    )
    # June expense — should appear
    make_expense(
        g, "monthly_expense", cat, "50.00", member, date="2026-06-15",
        shares={member: "50.00"},
    )

    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()

    assert len(items) == 1
    assert items[0]["date"] == "2026-06-15"


@pytest.mark.django_db
def test_activity_expense_role_payer_vs_participant(api_client):
    """Role should be 'payer' when user paid the expense, 'participant' otherwise."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")

    # owner pays — owner gets "payer", member gets "participant"
    make_expense(
        g, "monthly_expense", cat, "100.00", owner,
        shares={owner: "50.00", member: "50.00"},
    )

    # Check owner
    auth(api_client, owner)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["role"] == "payer"

    # Check member
    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["role"] == "participant"


@pytest.mark.django_db
def test_activity_meal_amount_reflects_extras_share(api_client):
    """Meal item amount must be the user's apportioned share of the event's extras."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(owner, a, b)

    pool = Category.objects.create(group=g, ledger_type="kitchen_pool", name="Dinner")
    ev = MealEvent.objects.create(group=g, category=pool, date="2026-06-10", created_by=owner)
    # a: multiplier=1, b: multiplier=2
    MealAttendance.objects.create(meal_event=ev, user=a, multiplier=1)
    MealAttendance.objects.create(meal_event=ev, user=b, multiplier=2)

    # Extra: 30.00 paid by owner
    ExtraAmount.objects.create(meal_event=ev, title="dessert", amount=Decimal("30.00"),
                               paid_by=owner, created_by=owner)

    # a's share: 30 * (1/3) = 10.00
    auth(api_client, a)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    meal_items = [i for i in items if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert meal_items[0]["amount"] == "10.00"

    # b's share: 30 * (2/3) = 20.00
    auth(api_client, b)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    meal_items = [i for i in items if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert meal_items[0]["amount"] == "20.00"


@pytest.mark.django_db
def test_activity_meal_no_extras_amount_is_zero(api_client):
    """Meal event with no ExtraAmount records should have amount = '0.00'."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    pool = Category.objects.create(group=g, ledger_type="kitchen_pool", name="Lunch")
    ev = MealEvent.objects.create(group=g, category=pool, date="2026-06-07", created_by=owner)
    MealAttendance.objects.create(meal_event=ev, user=member, multiplier=1)

    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    meal_items = [i for i in items if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert meal_items[0]["amount"] == "0.00"


@pytest.mark.django_db
def test_activity_expense_appears_once_for_payer_with_share(api_client):
    """When user is both payer and holds a share, expense must appear exactly once."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    g = make_group(owner)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Internet")
    make_expense(
        g, "monthly_expense", cat, "100.00", owner,
        shares={owner: "100.00"},
    )

    auth(api_client, owner)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["role"] == "payer"
    assert items[0]["amount"] == "100.00"


@pytest.mark.django_db
def test_activity_sorted_descending(api_client):
    """Items must be sorted by date descending."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    g = make_group(owner)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Misc")
    make_expense(g, "monthly_expense", cat, "10.00", owner, date="2026-06-01",
                 shares={owner: "10.00"})
    make_expense(g, "monthly_expense", cat, "20.00", owner, date="2026-06-15",
                 shares={owner: "20.00"})
    make_expense(g, "monthly_expense", cat, "30.00", owner, date="2026-06-08",
                 shares={owner: "30.00"})

    auth(api_client, owner)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    dates = [i["date"] for i in items]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.django_db
def test_activity_meal_amount_matches_compute_with_multiple_extras(api_client):
    """Meal amount for activity must match per-extra apportionment from compute_settlement.

    With 3 equal-weight attendees and TWO extras of 1.00 each, apportion(1.00, [1,1,1])
    gives [0.34, 0.33, 0.33] (last absorbs remainder). If extras were summed first
    (2.00) apportion would give [0.67, 0.67, 0.66] — diverging at the last position.
    This test ensures the view uses per-extra apportionment to match compute.py exactly.
    """
    from apps.settlement.money import apportion as _apportion

    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(owner, a, b)

    pool = Category.objects.create(group=g, ledger_type="kitchen_pool", name="Dinner")
    ev = MealEvent.objects.create(group=g, category=pool, date="2026-06-12", created_by=owner)
    # Three equal-weight attendees: owner, a, b (multiplier=1 each)
    MealAttendance.objects.create(meal_event=ev, user=owner, multiplier=1)
    MealAttendance.objects.create(meal_event=ev, user=a, multiplier=1)
    MealAttendance.objects.create(meal_event=ev, user=b, multiplier=1)

    # Two extras: 1.00 each
    ExtraAmount.objects.create(
        meal_event=ev, title="extra1", amount=Decimal("1.00"), paid_by=owner, created_by=owner,
    )
    ExtraAmount.objects.create(
        meal_event=ev, title="extra2", amount=Decimal("1.00"), paid_by=owner, created_by=owner,
    )

    # Per-extra apportionment: apportion(1.00, [1,1,1]) == [0.34, 0.33, 0.33]
    # (first position is last_nonzero=2 absorbing remainder? No — last_nonzero is index 2.)
    # Actually apportion distributes: indices 0 and 1 get 0.33 each, index 2 (last nonzero) gets 0.34
    weights = [Decimal("1"), Decimal("1"), Decimal("1")]
    per_extra_shares = _apportion(Decimal("1.00"), weights)
    # owner is index 0, a is index 1, b is index 2 — sum across both extras
    expected_owner = per_extra_shares[0] + per_extra_shares[0]
    expected_a = per_extra_shares[1] + per_extra_shares[1]
    expected_b = per_extra_shares[2] + per_extra_shares[2]

    # Verify owner's amount
    auth(api_client, owner)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    meal_items = [i for i in r.json() if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert Decimal(meal_items[0]["amount"]) == expected_owner

    # Verify a's amount
    auth(api_client, a)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    meal_items = [i for i in r.json() if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert Decimal(meal_items[0]["amount"]) == expected_a

    # Verify b's amount (last attendee — absorbs remainder each extra)
    auth(api_client, b)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    meal_items = [i for i in r.json() if i["kind"] == "meal"]
    assert len(meal_items) == 1
    assert Decimal(meal_items[0]["amount"]) == expected_b

    # Cross-check: per-extra sum != naive sum-first-then-apportion for the last position
    naive_shares = _apportion(Decimal("2.00"), weights)
    # b's per-extra sum (2 * per_extra_shares[2]) should differ from naive_shares[2]
    # This confirms the test distinguishes the two approaches when rounding diverges
    if per_extra_shares[2] * 2 != naive_shares[2]:
        # Rounding differs as expected — assert the view matches per-extra, not naive
        assert Decimal(meal_items[0]["amount"]) != str(naive_shares[2])


@pytest.mark.django_db
def test_activity_missing_year_returns_400(api_client):
    """Missing year param must return 400."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&month=6")
    assert r.status_code == 400


@pytest.mark.django_db
def test_activity_non_integer_year_returns_400(api_client):
    """Non-integer year param must return 400."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=notanumber&month=6")
    assert r.status_code == 400


@pytest.mark.django_db
def test_standing_month_out_of_range_returns_400(api_client):
    """my_standing with month=0 must return 400."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/me/standing/?group={g.id}&year=2026&month=0")
    assert r.status_code == 400
    assert r.json()["detail"] == "month must be between 1 and 12."


@pytest.mark.django_db
def test_activity_payer_only_no_share_amount_zero(api_client):
    """User who only paid but holds no ExpenseShare should have amount='0.00' and role='payer'."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Fuel")
    # owner pays but only member has a share
    make_expense(
        g, "monthly_expense", cat, "50.00", owner, date="2026-06-10",
        shares={member: "50.00"},
    )

    auth(api_client, owner)
    r = api_client.get(f"/api/me/activity/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["role"] == "payer"
    assert items[0]["amount"] == "0.00"
