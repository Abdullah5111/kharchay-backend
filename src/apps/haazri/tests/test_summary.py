import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category
from apps.haazri.models import MealEvent, MealAttendance, ExtraAmount

User = get_user_model()


def auth(c, u):
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="TestGroup", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def pool(g, name):
    return Category.objects.create(group=g, ledger_type="kitchen_pool", name=name)


def event(c, g, cat, date):
    r = c.post(f"/api/groups/{g.id}/haazri/", {"category": str(cat.id), "date": date}, format="json")
    return r.json()


@pytest.mark.django_db
def test_summary_units_and_extras(api_client):
    """Two members eat Lunch over 2 days; summary returns correct per_user units and extras_total."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(owner, a, b)
    lunch = pool(g, "Lunch")

    # Day 1: a(multiplier=1), b(multiplier=2)
    ev1 = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    MealAttendance.objects.create(meal_event=ev1, user=a, multiplier=1)
    MealAttendance.objects.create(meal_event=ev1, user=b, multiplier=2)

    # Day 2: only a(multiplier=1)
    ev2 = MealEvent.objects.create(group=g, category=lunch, date="2026-06-02", created_by=owner)
    MealAttendance.objects.create(meal_event=ev2, user=a, multiplier=1)

    # Add extras: 100 + 50 = 150
    ExtraAmount.objects.create(meal_event=ev1, amount="100.00", paid_by=a, created_by=owner)
    ExtraAmount.objects.create(meal_event=ev2, amount="50.00", paid_by=a, created_by=owner)

    auth(api_client, a)
    r = api_client.get(f"/api/groups/{g.id}/haazri/summary/?year=2026&month=6")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1

    pool_data = data[0]
    assert pool_data["total_units"] == 4  # a:2, b:2
    assert float(pool_data["extras_total"]) == 150.0

    per_user = {str(entry["user"]["id"]): entry["units"] for entry in pool_data["per_user"]}
    assert per_user[str(a.id)] == 2
    assert per_user[str(b.id)] == 2


@pytest.mark.django_db
def test_summary_non_member_gets_404(api_client):
    """Non-member gets 404 from summary endpoint."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    outsider = User.objects.create_user(email="outsider@e.com", name="Outsider")
    g = make_group(owner)
    lunch = pool(g, "Lunch")

    auth(api_client, outsider)
    r = api_client.get(f"/api/groups/{g.id}/haazri/summary/?year=2026&month=6")
    assert r.status_code == 404


@pytest.mark.django_db
def test_my_haazri_returns_own_rows(api_client):
    """My haazri endpoint returns only the caller's own rows for that group+month."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(owner, a, b)
    lunch = pool(g, "Lunch")

    ev1 = MealEvent.objects.create(group=g, category=lunch, date="2026-06-01", created_by=owner)
    MealAttendance.objects.create(meal_event=ev1, user=a, multiplier=1)
    MealAttendance.objects.create(meal_event=ev1, user=b, multiplier=2)

    ev2 = MealEvent.objects.create(group=g, category=lunch, date="2026-06-02", created_by=owner)
    MealAttendance.objects.create(meal_event=ev2, user=a, multiplier=1)

    auth(api_client, a)
    r = api_client.get(f"/api/me/haazri/?group={g.id}&year=2026&month=6")
    assert r.status_code == 200
    rows = r.json()
    # a should see 2 rows (both ev1 and ev2)
    assert len(rows) == 2
    for row in rows:
        assert row["user"]["id"] == str(a.id)


@pytest.mark.django_db
def test_my_haazri_group_filter_excludes_other_groups(api_client):
    """My haazri with group filter excludes attendance from other groups."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    a = User.objects.create_user(email="a@e.com", name="A")
    g1 = make_group(owner, a)
    g2 = make_group(owner, a)
    lunch1 = pool(g1, "Lunch")
    lunch2 = pool(g2, "Lunch")

    ev1 = MealEvent.objects.create(group=g1, category=lunch1, date="2026-06-01", created_by=owner)
    MealAttendance.objects.create(meal_event=ev1, user=a, multiplier=1)

    ev2 = MealEvent.objects.create(group=g2, category=lunch2, date="2026-06-01", created_by=owner)
    MealAttendance.objects.create(meal_event=ev2, user=a, multiplier=1)

    auth(api_client, a)
    r = api_client.get(f"/api/me/haazri/?group={g1.id}&year=2026&month=6")
    assert r.status_code == 200
    rows = r.json()
    # Should only see g1's row
    assert len(rows) == 1
    assert rows[0]["event_id"] == str(ev1.id)


@pytest.mark.django_db
def test_summary_no_fanout_same_event_multi_attendee_multi_extra(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = event(api_client, g, lunch, date="2026-06-05")["id"]
    # two attendees on the same event: a x1, b x2  -> total units 3
    api_client.put(f"/api/haazri/{eid}/attendance/", {"entries": [
        {"user": str(a.id), "multiplier": 1}, {"user": str(b.id), "multiplier": 2}]}, format="json")
    # two extras on the SAME event -> extras_total must be 30.00 (NOT multiplied by attendees)
    api_client.post(f"/api/haazri/{eid}/extras/", {"title": "juice", "amount": "10.00", "paid_by": str(a.id)}, format="json")
    api_client.post(f"/api/haazri/{eid}/extras/", {"title": "fruit", "amount": "20.00", "paid_by": str(a.id)}, format="json")
    summary = api_client.get(f"/api/groups/{g.id}/haazri/summary/?year=2026&month=6").json()
    lunch_row = next(r for r in summary if r["category_name"] == "Lunch")
    assert lunch_row["total_units"] == 3  # 1 + 2, NOT inflated by extras
    from decimal import Decimal
    assert Decimal(str(lunch_row["extras_total"])) == Decimal("30.00")  # 10 + 20, NOT x attendees
    per = {u["user"]["id"]: u["units"] for u in lunch_row["per_user"]}
    assert per[str(a.id)] == 1 and per[str(b.id)] == 2
