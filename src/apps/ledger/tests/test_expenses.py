import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category, Expense

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

def make_group(owner, *members):
    g = Group.objects.create(name="House 8", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g

def cat(g, kind, name):
    return Category.objects.create(group=g, ledger_type=kind, name=name)

@pytest.mark.django_db
def test_equal_split_creates_shares(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    c = cat(g, "monthly_expense", "Rent")
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "June rent",
        "amount": "10000.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id), str(b.id)],
    }, format="json")
    assert r.status_code == 201
    exp = Expense.objects.get(id=r.json()["id"])
    shares = {str(s.user_id): s.amount for s in exp.shares.all()}
    assert shares[str(a.id)] + shares[str(b.id)] == Decimal("10000.00")
    assert shares[str(a.id)] == Decimal("5000.00")

@pytest.mark.django_db
def test_custom_split_must_sum_to_amount(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    c = cat(g, "monthly_expense", "Rent")
    auth(api_client, a)
    bad = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "rent",
        "amount": "10000.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "custom", "shares": [{"user": str(a.id), "amount": "4000.00"}, {"user": str(b.id), "amount": "5000.00"}],
    }, format="json")
    assert bad.status_code == 400

@pytest.mark.django_db
def test_kitchen_expense_has_no_shares(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    pool = cat(g, "kitchen_pool", "Lunch")
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "kitchen", "category": str(pool.id), "title": "veg",
        "amount": "1200.00", "paid_by": str(a.id), "date": "2026-06-05",
    }, format="json")
    assert r.status_code == 201
    assert Expense.objects.get(id=r.json()["id"]).shares.count() == 0

@pytest.mark.django_db
def test_member_cannot_create_expense(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    c = cat(g, "monthly_expense", "Rent")
    auth(api_client, b)
    assert api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(c.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id)],
    }, format="json").status_code == 403


@pytest.mark.django_db
def test_equal_split_rounding_remainder(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    c = User.objects.create_user(email="c@e.com", name="C")
    g = make_group(a, b, c)
    cat_ = cat(g, "monthly_expense", "Rent")
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(cat_.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id), str(b.id), str(c.id)],
    }, format="json")
    assert r.status_code == 201
    from apps.ledger.models import Expense
    from decimal import Decimal
    exp = Expense.objects.get(id=r.json()["id"])
    amts = sorted(s.amount for s in exp.shares.all())
    assert amts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(amts) == Decimal("100.00")


@pytest.mark.django_db
def test_category_kind_mismatch_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    pool = cat(g, "kitchen_pool", "Lunch")  # kitchen_pool category...
    auth(api_client, a)
    # ...used on a monthly_expense ledger -> 400
    r = api_client.post(f"/api/groups/{g.id}/expenses/", {
        "ledger_type": "monthly_expense", "category": str(pool.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id)],
    }, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_cross_group_category_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g1 = make_group(a)
    g2 = make_group(a)
    other_cat = cat(g2, "monthly_expense", "Rent")  # belongs to g2
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g1.id}/expenses/", {  # used on g1 -> 400
        "ledger_type": "monthly_expense", "category": str(other_cat.id), "title": "x",
        "amount": "100.00", "paid_by": str(a.id), "date": "2026-06-05",
        "split_type": "equal", "involved": [str(a.id)],
    }, format="json")
    assert r.status_code == 400
