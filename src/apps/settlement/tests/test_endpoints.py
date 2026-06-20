import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Expense, ExpenseShare, LedgerPeriod
from apps.notifications.models import Notification

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="Test", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="admin", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def finalize_all(group, year, month):
    for lt in ["monthly_expense", "kitchen", "workplace"]:
        LedgerPeriod.objects.create(group=group, ledger_type=lt, year=year, month=month, status="finalized")


def add_expense(group, owner, member, year=2026, month=1):
    """Create a simple equal-split expense so compute returns non-trivial data."""
    cat = Category.objects.create(group=group, ledger_type="monthly_expense", name="Rent")
    e = Expense.objects.create(
        group=group,
        ledger_type="monthly_expense",
        category=cat,
        amount=Decimal("100.00"),
        paid_by=owner,
        date=f"{year}-{month:02d}-05",
        split_type="equal",
        created_by=owner,
    )
    ExpenseShare.objects.create(expense=e, user=owner, amount=Decimal("50.00"))
    ExpenseShare.objects.create(expense=e, user=member, amount=Decimal("50.00"))
    return e


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_preview_non_member_returns_404(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    outsider = User.objects.create_user(email="outsider@e.com", name="Outsider")
    g = make_group(owner)
    auth(api_client, outsider)
    r = api_client.get(f"/api/groups/{g.id}/settlement/?year=2026&month=1")
    assert r.status_code == 404


@pytest.mark.django_db
def test_preview_member_non_admin_returns_403(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)
    r = api_client.get(f"/api/groups/{g.id}/settlement/?year=2026&month=1")
    assert r.status_code == 403


@pytest.mark.django_db
def test_preview_admin_returns_200(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    add_expense(g, owner, member)
    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/settlement/?year=2026&month=1")
    assert r.status_code == 200
    data = r.json()
    assert "year" in data
    assert "month" in data
    assert "finalized" in data
    assert "lines" in data
    assert "transfers" in data


@pytest.mark.django_db
def test_generate_before_all_finalized_returns_400(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    # Only finalize one of the three required periods
    LedgerPeriod.objects.create(group=g, ledger_type="monthly_expense", year=2026, month=1, status="finalized")
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/settlement/2026/1/generate/")
    assert r.status_code == 400
    assert "Finalize all ledgers" in r.json()["detail"]


@pytest.mark.django_db
def test_generate_after_finalize_creates_records(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    add_expense(g, owner, member)
    finalize_all(g, 2026, 1)
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/settlement/2026/1/generate/")
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert "status" in data
    assert data["status"] == "draft"
    assert len(data["lines"]) == 2
    assert len(data["transfers"]) >= 1

    from apps.settlement.models import Settlement, SettlementLine, Transfer
    settlement = Settlement.objects.get(id=data["id"])
    assert settlement.group == g
    assert SettlementLine.objects.filter(settlement=settlement).count() == 2
    assert Transfer.objects.filter(settlement=settlement).count() >= 1

    # Notification created for the OTHER participant (member), not the generator (owner)
    notifs = Notification.objects.filter(type="settlement_ready")
    notif_user_ids = set(str(n.user_id) for n in notifs)
    assert str(member.id) in notif_user_ids
    assert str(owner.id) not in notif_user_ids


@pytest.mark.django_db
def test_generate_twice_replaces(api_client):
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    add_expense(g, owner, member)
    finalize_all(g, 2026, 1)
    auth(api_client, owner)

    r1 = api_client.post(f"/api/groups/{g.id}/settlement/2026/1/generate/")
    assert r1.status_code == 201
    id1 = r1.json()["id"]

    # Second call must not raise IntegrityError
    r2 = api_client.post(f"/api/groups/{g.id}/settlement/2026/1/generate/")
    assert r2.status_code == 201
    id2 = r2.json()["id"]

    # Old settlement is gone, new one exists
    from apps.settlement.models import Settlement
    assert not Settlement.objects.filter(id=id1).exists()
    assert Settlement.objects.filter(id=id2).exists()


@pytest.mark.django_db
def test_preview_month_out_of_range_high_returns_400(api_client):
    """settlement_preview with month=13 must return 400."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    g = make_group(owner)
    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/settlement/?year=2026&month=13")
    assert r.status_code == 400
    assert r.json()["detail"] == "month must be between 1 and 12."


@pytest.mark.django_db
def test_preview_month_out_of_range_zero_returns_400(api_client):
    """settlement_preview with month=0 must return 400."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    g = make_group(owner)
    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/settlement/?year=2026&month=0")
    assert r.status_code == 400
    assert r.json()["detail"] == "month must be between 1 and 12."


@pytest.mark.django_db
def test_generate_returns_201(api_client):
    """generate_settlement must return HTTP 201 on success."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)
    add_expense(g, owner, member)
    finalize_all(g, 2026, 1)
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/settlement/2026/1/generate/")
    assert r.status_code == 201
