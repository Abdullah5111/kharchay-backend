import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.ledger.models import Category

User = get_user_model()


def auth(c, u):
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="H", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def pool(g, name):
    return Category.objects.create(group=g, ledger_type="kitchen_pool", name=name)


def create_event(client, g, cat, date="2026-06-10"):
    r = client.post(f"/api/groups/{g.id}/haazri/", {"category": str(cat.id), "date": date}, format="json")
    assert r.status_code in (200, 201), r.json()
    return r.json()["id"]


@pytest.mark.django_db
def test_admin_adds_extra_201(api_client):
    """Admin can add an extra amount to an event; returns 201 with the created extra."""
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    r = api_client.post(
        f"/api/haazri/{eid}/extras/",
        {"title": "Juice", "amount": "50.00", "paid_by": str(a.id)},
        format="json",
    )
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["title"] == "Juice"
    assert Decimal(data["amount"]) == Decimal("50.00")
    assert data["paid_by"]["id"] == str(a.id)
    assert "id" in data


@pytest.mark.django_db
def test_extra_appears_in_event_detail(api_client):
    """After adding an extra, the event detail endpoint returns it under extras."""
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    api_client.post(
        f"/api/haazri/{eid}/extras/",
        {"title": "Snacks", "amount": "30.00", "paid_by": str(a.id)},
        format="json",
    )

    r = api_client.get(f"/api/haazri/{eid}/")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert "extras" in data
    assert len(data["extras"]) == 1
    assert data["extras"][0]["title"] == "Snacks"
    assert Decimal(data["extras"][0]["amount"]) == Decimal("30.00")
    # Also check attendance key is present
    assert "attendance" in data


@pytest.mark.django_db
def test_member_cannot_add_extra_403(api_client):
    """A regular member (non-admin) gets 403 when trying to add an extra."""
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    g = make_group(a, b)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    auth(api_client, b)  # member, not admin
    r = api_client.post(
        f"/api/haazri/{eid}/extras/",
        {"title": "Tea", "amount": "10.00", "paid_by": str(b.id)},
        format="json",
    )
    assert r.status_code == 403, r.json()


@pytest.mark.django_db
def test_nonmember_payer_rejected_400(api_client):
    """paid_by must be an active member of the event's group; non-member → 400."""
    a = User.objects.create_user(email="a@e.com", name="A")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    r = api_client.post(
        f"/api/haazri/{eid}/extras/",
        {"amount": "20.00", "paid_by": str(outsider.id)},
        format="json",
    )
    assert r.status_code == 400, r.json()


@pytest.mark.django_db
def test_zero_amount_rejected_400(api_client):
    """amount of 0.00 is invalid (must be > 0); expect 400."""
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    r = api_client.post(
        f"/api/haazri/{eid}/extras/",
        {"title": "Nothing", "amount": "0.00", "paid_by": str(a.id)},
        format="json",
    )
    assert r.status_code == 400, r.json()


@pytest.mark.django_db
def test_nonmember_cannot_view_event_detail_404(api_client):
    """A user who is not a member of the group gets 404 on the event detail endpoint."""
    a = User.objects.create_user(email="a@e.com", name="A")
    outsider = User.objects.create_user(email="o@e.com", name="O")
    g = make_group(a)
    lunch = pool(g, "Lunch")
    auth(api_client, a)
    eid = create_event(api_client, g, lunch)

    auth(api_client, outsider)
    r = api_client.get(f"/api/haazri/{eid}/")
    assert r.status_code == 404, r.json()
