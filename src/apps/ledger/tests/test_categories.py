import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

def make_group(owner, *members):
    g = Group.objects.create(name="House 8", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g

@pytest.mark.django_db
def test_admin_creates_and_lists_categories(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/categories/",
        {"ledger_type": "monthly_expense", "name": "Rent"}, format="json")
    assert r.status_code == 201
    listing = api_client.get(f"/api/groups/{g.id}/categories/?ledger=monthly_expense").json()
    assert [c["name"] for c in listing] == ["Rent"]
    # other ledger kind is empty
    assert api_client.get(f"/api/groups/{g.id}/categories/?ledger=kitchen_pool").json() == []

@pytest.mark.django_db
def test_member_cannot_create_category(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    auth(api_client, b)
    assert api_client.post(f"/api/groups/{g.id}/categories/",
        {"ledger_type": "monthly_expense", "name": "Rent"}, format="json").status_code == 403

@pytest.mark.django_db
def test_non_member_cannot_view_categories(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a)
    auth(api_client, outsider)
    assert api_client.get(f"/api/groups/{g.id}/categories/?ledger=monthly_expense").status_code == 404


@pytest.mark.django_db
def test_invalid_ledger_kind_rejected(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    auth(api_client, a)
    assert api_client.get(f"/api/groups/{g.id}/categories/?ledger=bogus").status_code == 400


@pytest.mark.django_db
def test_inline_add_existing_returns_200(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    auth(api_client, a)
    first = api_client.post(f"/api/groups/{g.id}/categories/", {"ledger_type": "monthly_expense", "name": "Rent"}, format="json")
    assert first.status_code == 201
    again = api_client.post(f"/api/groups/{g.id}/categories/", {"ledger_type": "monthly_expense", "name": "Rent"}, format="json")
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
