import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category

User = get_user_model()

def auth(c, u): c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")

def make_group(owner, *members):
    g = Group.objects.create(name="H", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g

def add_expense(c, g, cat, a, date="2026-06-05"):
    return c.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(cat.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": date,
        "split_type": "equal", "involved": [str(a.id)],
    }, format="json")

@pytest.mark.django_db
def test_finalize_locks_the_month(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    assert add_expense(api_client, g, cat, a).status_code == 201
    assert api_client.post(f"/api/groups/{g.id}/periods/monthly_expense/2026/6/finalize/").status_code == 200
    # period shows finalized
    periods = api_client.get(f"/api/groups/{g.id}/periods/?ledger=monthly_expense").json()
    assert any(p["year"] == 2026 and p["month"] == 6 and p["status"] == "finalized" for p in periods)
    # new expense in the locked month is rejected
    assert add_expense(api_client, g, cat, a).status_code == 403

@pytest.mark.django_db
def test_member_cannot_finalize(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    auth(api_client, b)
    assert api_client.post(f"/api/groups/{g.id}/periods/monthly_expense/2026/6/finalize/").status_code == 403

@pytest.mark.django_db
def test_non_member_cannot_list_periods(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a)
    auth(api_client, outsider)
    assert api_client.get(f"/api/groups/{g.id}/periods/?ledger=monthly_expense").status_code == 404
