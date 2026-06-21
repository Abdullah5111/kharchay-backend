import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.notifications.models import Notification
from apps.payments.models import Payment

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (verbatim from test_submit.py)
# ---------------------------------------------------------------------------

def auth(c, u):
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="TestGroup", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


def make_payment(group, user, status="submitted"):
    return Payment.objects.create(
        group=group,
        user=user,
        year=2026,
        month=6,
        amount=Decimal("500.00"),
        status=status,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_approves_submitted_payment_200(api_client):
    """Admin approves a submitted payment → 200, status=approved, reviewed_by set, payer notified."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    payer = User.objects.create_user(email="payer@e.com", name="Payer")
    g = make_group(owner, payer)
    payment = make_payment(g, payer)

    auth(api_client, owner)
    r = api_client.post(f"/api/payments/{payment.id}/approve/", {}, format="json")
    assert r.status_code == 200

    data = r.json()
    assert data["status"] == "approved"
    assert data["reviewed_by"] is not None
    assert data["reviewed_by"]["id"] == str(owner.id)
    assert data["reviewed_at"] is not None

    payment.refresh_from_db()
    assert payment.status == "approved"
    assert payment.reviewed_by == owner
    assert payment.reviewed_at is not None

    # Payer gets payment_approved notification
    assert Notification.objects.filter(user=payer, type="payment_approved").count() == 1
    # Admin (approver) should NOT be notified
    assert Notification.objects.filter(user=owner, type="payment_approved").count() == 0


@pytest.mark.django_db
def test_admin_rejects_with_note_200(api_client):
    """Admin rejects a submitted payment with a note → 200, status=rejected, note stored, payer notified."""
    owner = User.objects.create_user(email="owner2@e.com", name="Owner2")
    payer = User.objects.create_user(email="payer2@e.com", name="Payer2")
    g = make_group(owner, payer)
    payment = make_payment(g, payer)

    auth(api_client, owner)
    r = api_client.post(
        f"/api/payments/{payment.id}/reject/",
        {"review_note": "Insufficient proof."},
        format="json",
    )
    assert r.status_code == 200

    data = r.json()
    assert data["status"] == "rejected"
    assert data["review_note"] == "Insufficient proof."
    assert data["reviewed_by"] is not None
    assert data["reviewed_at"] is not None

    payment.refresh_from_db()
    assert payment.status == "rejected"
    assert payment.review_note == "Insufficient proof."
    assert payment.reviewed_by == owner

    # Payer gets payment_rejected notification
    assert Notification.objects.filter(user=payer, type="payment_rejected").count() == 1


@pytest.mark.django_db
def test_approve_already_approved_payment_400(api_client):
    """Approving an already-approved payment → 400."""
    owner = User.objects.create_user(email="owner3@e.com", name="Owner3")
    payer = User.objects.create_user(email="payer3@e.com", name="Payer3")
    g = make_group(owner, payer)
    payment = make_payment(g, payer, status="approved")

    auth(api_client, owner)
    r = api_client.post(f"/api/payments/{payment.id}/approve/", {}, format="json")
    assert r.status_code == 400
    assert "submitted" in r.json()["detail"].lower()


@pytest.mark.django_db
def test_reject_already_rejected_payment_400(api_client):
    """Rejecting an already-rejected payment → 400."""
    owner = User.objects.create_user(email="owner4@e.com", name="Owner4")
    payer = User.objects.create_user(email="payer4@e.com", name="Payer4")
    g = make_group(owner, payer)
    payment = make_payment(g, payer, status="rejected")

    auth(api_client, owner)
    r = api_client.post(f"/api/payments/{payment.id}/reject/", {}, format="json")
    assert r.status_code == 400
    assert "submitted" in r.json()["detail"].lower()


@pytest.mark.django_db
def test_non_admin_member_approve_403(api_client):
    """Non-admin member trying to approve → 403."""
    owner = User.objects.create_user(email="owner5@e.com", name="Owner5")
    member = User.objects.create_user(email="member5@e.com", name="Member5")
    g = make_group(owner, member)
    payment = make_payment(g, owner)

    auth(api_client, member)
    r = api_client.post(f"/api/payments/{payment.id}/approve/", {}, format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_non_member_approve_404(api_client):
    """Non-member trying to approve → 404 (no existence leak)."""
    owner = User.objects.create_user(email="owner6@e.com", name="Owner6")
    outsider = User.objects.create_user(email="outsider6@e.com", name="Outsider6")
    g = make_group(owner)
    payment = make_payment(g, owner)

    auth(api_client, outsider)
    r = api_client.post(f"/api/payments/{payment.id}/approve/", {}, format="json")
    assert r.status_code == 404


@pytest.mark.django_db
def test_unknown_payment_id_404(api_client):
    """Unknown payment_id → 404."""
    user = User.objects.create_user(email="user7@e.com", name="User7")
    auth(api_client, user)

    import uuid
    fake_id = str(uuid.uuid4())
    r = api_client.post(f"/api/payments/{fake_id}/approve/", {}, format="json")
    assert r.status_code == 404
