import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Contribution, Expense, ExpenseShare
from apps.settlement.compute import compute_settlement

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="Test", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="admin", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_create_management_expense(api_client):
    owner = User.objects.create_user(email="o@e.com", name="Owner")
    g = make_group(owner)
    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(cat.id), "amount": "100",
        "paid_by_management": True, "date": "2026-01-05",
        "split_type": "equal", "involved": [str(owner.id)],
    }, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["paid_by_management"] is True
    assert body["paid_by"] is None


@pytest.mark.django_db
def test_expense_requires_payer_or_management(api_client):
    owner = User.objects.create_user(email="o@e.com", name="Owner")
    g = make_group(owner)
    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(cat.id), "amount": "100",
        "date": "2026-01-05", "split_type": "equal", "involved": [str(owner.id)],
    }, format="json")
    assert r.status_code == 400  # neither paid_by nor management


@pytest.mark.django_db
def test_contribution_and_fund_summary(api_client):
    owner = User.objects.create_user(email="o@e.com", name="Owner")
    member = User.objects.create_user(email="m@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, owner)
    r = api_client.post(f"/api/groups/{g.id}/contributions/",
                        {"user": str(member.id), "amount": "200", "date": "2026-01-10"}, format="json")
    assert r.status_code == 201, r.content
    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    Expense.objects.create(group=g, ledger_type="monthly_expense", category=cat, amount=Decimal("50.00"),
                           paid_by=None, paid_by_management=True, date="2026-01-05",
                           split_type="equal", created_by=owner)
    r = api_client.get(f"/api/groups/{g.id}/fund/?year=2026&month=1")
    assert r.status_code == 200
    b = r.json()
    assert b["total_contributed"] == "200.00"
    assert b["total_spent"] == "50.00"
    assert b["balance"] == "150.00"
    assert len(b["per_member"]) == 1
    assert b["per_member"][0]["total"] == "200.00"


@pytest.mark.django_db
def test_contribution_requires_admin(api_client):
    owner = User.objects.create_user(email="o@e.com", name="Owner")
    member = User.objects.create_user(email="m@e.com", name="Member")
    g = make_group(owner, member)
    auth(api_client, member)  # plain member
    r = api_client.post(f"/api/groups/{g.id}/contributions/",
                        {"user": str(member.id), "amount": "50", "date": "2026-01-10"}, format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_settlement_credits_contribution_not_management_payer():
    owner = User.objects.create_user(email="o@e.com", name="Owner")
    member = User.objects.create_user(email="m@e.com", name="Member")
    g = make_group(owner, member)
    # member contributes 100 into the fund
    Contribution.objects.create(group=g, user=member, amount=Decimal("100.00"),
                                date="2026-01-10", created_by=owner)
    # a 100 expense paid from the fund, split equally (50 each)
    cat = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    e = Expense.objects.create(group=g, ledger_type="monthly_expense", category=cat, amount=Decimal("100.00"),
                               paid_by=None, paid_by_management=True, date="2026-01-05",
                               split_type="equal", created_by=owner)
    ExpenseShare.objects.create(expense=e, user=owner, amount=Decimal("50.00"))
    ExpenseShare.objects.create(expense=e, user=member, amount=Decimal("50.00"))

    lines = compute_settlement(g, 2026, 1)["lines"]
    # Owner: owes their 50 share, credited nothing (fund paid) -> net +50
    assert lines[owner.id]["paid_total"] == Decimal("0.00")
    assert lines[owner.id]["owed_total"] == Decimal("50.00")
    assert lines[owner.id]["net"] == Decimal("50.00")
    # Member: owes 50 share but pre-paid 100 into fund -> net -50 (owed 50 back)
    assert lines[member.id]["paid_total"] == Decimal("100.00")
    assert lines[member.id]["owed_total"] == Decimal("50.00")
    assert lines[member.id]["net"] == Decimal("-50.00")
    # Books balance: fund fully spent
    assert lines[owner.id]["net"] + lines[member.id]["net"] == Decimal("0.00")
