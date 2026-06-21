import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Expense

User = get_user_model()

def auth(c, u): c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")

def make_group(owner, *members):
    g = Group.objects.create(name="H", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g

def make_expense(client, g, c, a, amount="100.00", date="2026-06-05"):
    return client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "x",
        "amount": amount, "paid_by": str(a.id), "date": date,
        "split_type": "equal", "involved": [str(a.id)],
    }, format="json").json()

@pytest.mark.django_db
def test_list_filters_by_month(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    make_expense(api_client, g, c, a, date="2026-06-05")
    make_expense(api_client, g, c, a, date="2026-05-05")
    june = api_client.get(f"/api/groups/{g.id}/expenses/?ledger=monthly_expense&year=2026&month=6").json()
    assert len(june) == 1

@pytest.mark.django_db
def test_update_recomputes_shares(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a, amount="100.00")["id"]
    r = api_client.patch(f"/api/expenses/{eid}/", {
        "amount": "200.00", "split_type": "equal", "involved": [str(a.id), str(b.id)],
    }, format="json")
    assert r.status_code == 200
    exp = Expense.objects.get(id=eid)
    assert sum(s.amount for s in exp.shares.all()) == Decimal("200.00")
    assert exp.shares.count() == 2

@pytest.mark.django_db
def test_delete_expense(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a)["id"]
    assert api_client.delete(f"/api/expenses/{eid}/").status_code == 200
    assert not Expense.objects.filter(id=eid).exists()


@pytest.mark.django_db
def test_patch_amount_only_recomputes_shares(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    # equal split between a and b at 100 -> 50/50
    eid = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id), str(b.id)],
    }, format="json").json()["id"]
    # change ONLY the amount -> shares must re-sum to 200 across the same 2 members
    r = api_client.patch(f"/api/expenses/{eid}/", {"amount": "200.00"}, format="json")
    assert r.status_code == 200
    exp = Expense.objects.get(id=eid)
    assert exp.shares.count() == 2
    assert sum(s.amount for s in exp.shares.all()) == Decimal("200.00")


@pytest.mark.django_db
def test_finalized_period_blocks_patch_and_delete(api_client):
    from apps.ledger.models import LedgerPeriod
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a, date="2026-06-05")["id"]
    LedgerPeriod.objects.filter(group=g, ledger_type="monthly_expense", year=2026, month=6).update(status="finalized")
    assert api_client.patch(f"/api/expenses/{eid}/", {"amount": "5.00"}, format="json").status_code == 403
    assert api_client.delete(f"/api/expenses/{eid}/").status_code == 403


@pytest.mark.django_db
def test_non_admin_cannot_modify_and_non_member_404(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a)["id"]
    auth(api_client, b)  # member but not admin
    assert api_client.patch(f"/api/expenses/{eid}/", {"amount": "5.00"}, format="json").status_code == 403
    auth(api_client, outsider)  # non-member
    assert api_client.get(f"/api/expenses/{eid}/").status_code == 404


@pytest.mark.django_db
def test_custom_duplicate_member_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "custom", "shares": [{"user": str(a.id), "amount": "50.00"}, {"user": str(a.id), "amount": "50.00"}],
    }, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_custom_negative_share_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "custom", "shares": [{"user": str(a.id), "amount": "200.00"}, {"user": str(b.id), "amount": "-100.00"}],
    }, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_patch_amount_to_zero_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a)["id"]
    assert api_client.patch(f"/api/expenses/{eid}/", {"amount": "0.00"}, format="json").status_code == 400


@pytest.mark.django_db
def test_failed_custom_update_leaves_amount_unchanged(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a, amount="100.00")["id"]
    # custom shares that don't sum to the new amount -> 400, and amount must NOT have changed
    r = api_client.patch(f"/api/expenses/{eid}/", {
        "amount": "300.00", "split_type": "custom",
        "shares": [{"user": str(a.id), "amount": "100.00"}, {"user": str(b.id), "amount": "100.00"}],
    }, format="json")
    assert r.status_code == 400
    exp = Expense.objects.get(id=eid)
    assert exp.amount == Decimal("100.00")
    assert sum(s.amount for s in exp.shares.all()) == Decimal("100.00")


@pytest.mark.django_db
def test_patch_date_into_finalized_month_blocked(api_client):
    from apps.ledger.models import LedgerPeriod
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a); c = Category.objects.create(group=g, ledger_type="monthly_expense", name="Rent")
    auth(api_client, a)
    eid = make_expense(api_client, g, c, a, date="2026-06-05")["id"]
    # finalize JULY (a different, empty month) directly
    LedgerPeriod.objects.create(group=g, ledger_type="monthly_expense", year=2026, month=7, status="finalized")
    # moving the June expense into finalized July must be blocked
    assert api_client.patch(f"/api/expenses/{eid}/", {"date": "2026-07-10"}, format="json").status_code == 403
