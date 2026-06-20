import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership
from apps.notifications.models import Notification
from apps.payments.models import Payment

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers (verbatim from haazri/tests/test_summary.py)
# ---------------------------------------------------------------------------

def auth(c, u):
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")


def make_group(owner, *members):
    g = Group.objects.create(name="TestGroup", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_submit_without_proof_201_and_admins_notified(api_client):
    """Member submits without proof → 201; group admins receive payment_submitted notification."""
    owner = User.objects.create_user(email="owner@e.com", name="Owner")
    member = User.objects.create_user(email="member@e.com", name="Member")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "500.00", "year": 2026, "month": 6},
        format="json",
    )
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "submitted"
    assert data["proof_url"] is None

    # Owner should have received a payment_submitted notification
    assert Notification.objects.filter(user=owner, type="payment_submitted").count() == 1
    # Member (payer) should NOT be notified
    assert Notification.objects.filter(user=member, type="payment_submitted").count() == 0


@pytest.mark.django_db
def test_submit_with_valid_png_201_proof_url_non_null(api_client, settings, tmp_path):
    """Member submits with a valid PNG → 201; proof_url is non-null."""
    settings.MEDIA_ROOT = str(tmp_path)
    owner = User.objects.create_user(email="owner2@e.com", name="Owner2")
    member = User.objects.create_user(email="member2@e.com", name="Member2")
    g = make_group(owner, member)

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    proof_file = SimpleUploadedFile("proof.png", png_bytes, content_type="image/png")

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "1000.00", "year": 2026, "month": 6, "proof": proof_file},
        format="multipart",
    )
    assert r.status_code == 201
    data = r.json()
    assert data["proof_url"] is not None
    assert "proofs/" in data["proof_url"]


@pytest.mark.django_db
def test_submit_bad_image_type_400(api_client):
    """Submit with a non-image file type → 400."""
    owner = User.objects.create_user(email="owner3@e.com", name="Owner3")
    member = User.objects.create_user(email="member3@e.com", name="Member3")
    g = make_group(owner, member)

    bad_file = SimpleUploadedFile("file.txt", b"not an image", content_type="text/plain")

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "100.00", "year": 2026, "month": 6, "proof": bad_file},
        format="multipart",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_submit_amount_zero_400(api_client):
    """Submit with amount = 0 → 400."""
    owner = User.objects.create_user(email="owner4@e.com", name="Owner4")
    member = User.objects.create_user(email="member4@e.com", name="Member4")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "0.00", "year": 2026, "month": 6},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_submit_negative_amount_400(api_client):
    """Submit with negative amount → 400."""
    owner = User.objects.create_user(email="owner5@e.com", name="Owner5")
    member = User.objects.create_user(email="member5@e.com", name="Member5")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "-100.00", "year": 2026, "month": 6},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_submit_month_13_400(api_client):
    """Submit with month = 13 → 400."""
    owner = User.objects.create_user(email="owner6@e.com", name="Owner6")
    member = User.objects.create_user(email="member6@e.com", name="Member6")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "100.00", "year": 2026, "month": 13},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_submit_non_member_404(api_client):
    """Non-member submitting → 404 (no existence leak)."""
    owner = User.objects.create_user(email="owner7@e.com", name="Owner7")
    outsider = User.objects.create_user(email="outsider@e.com", name="Outsider")
    g = make_group(owner)

    auth(api_client, outsider)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "100.00", "year": 2026, "month": 6},
        format="json",
    )
    assert r.status_code == 404


@pytest.mark.django_db
def test_get_group_payments_admin_200(api_client):
    """GET group payments as admin → 200 with list."""
    owner = User.objects.create_user(email="owner8@e.com", name="Owner8")
    member = User.objects.create_user(email="member8@e.com", name="Member8")
    g = make_group(owner, member)
    Payment.objects.create(group=g, user=member, year=2026, month=6, amount=Decimal("500.00"))

    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/payments/")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1


@pytest.mark.django_db
def test_get_group_payments_non_admin_403(api_client):
    """GET group payments as non-admin member → 403."""
    owner = User.objects.create_user(email="owner9@e.com", name="Owner9")
    member = User.objects.create_user(email="member9@e.com", name="Member9")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.get(f"/api/groups/{g.id}/payments/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_get_group_payments_non_member_404(api_client):
    """GET group payments as non-member → 404."""
    owner = User.objects.create_user(email="owner10@e.com", name="Owner10")
    outsider = User.objects.create_user(email="outsider10@e.com", name="Outsider10")
    g = make_group(owner)

    auth(api_client, outsider)
    r = api_client.get(f"/api/groups/{g.id}/payments/")
    assert r.status_code == 404


@pytest.mark.django_db
def test_my_payments_returns_only_caller_payments(api_client):
    """GET me/payments?group= returns only the caller's own payments."""
    owner = User.objects.create_user(email="owner11@e.com", name="Owner11")
    member_a = User.objects.create_user(email="membera@e.com", name="MemberA")
    member_b = User.objects.create_user(email="memberb@e.com", name="MemberB")
    g = make_group(owner, member_a, member_b)

    Payment.objects.create(group=g, user=member_a, year=2026, month=6, amount=Decimal("300.00"))
    Payment.objects.create(group=g, user=member_b, year=2026, month=6, amount=Decimal("200.00"))

    auth(api_client, member_a)
    r = api_client.get(f"/api/me/payments/?group={g.id}")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["amount"] == "300.00"


@pytest.mark.django_db
def test_my_payments_missing_group_400(api_client):
    """GET me/payments without group param → 400."""
    user = User.objects.create_user(email="user12@e.com", name="User12")
    auth(api_client, user)
    r = api_client.get("/api/me/payments/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_get_group_payments_invalid_year_400(api_client):
    """GET group payments with ?year=abc as admin → 400 with descriptive detail."""
    owner = User.objects.create_user(email="owner13@e.com", name="Owner13")
    g = make_group(owner)

    auth(api_client, owner)
    r = api_client.get(f"/api/groups/{g.id}/payments/?year=abc")
    assert r.status_code == 400
    assert r.json()["detail"] == "year and month must be integers."


@pytest.mark.django_db
def test_my_payments_invalid_year_400(api_client):
    """GET me/payments?group={id}&year=abc → 400 with descriptive detail."""
    owner = User.objects.create_user(email="owner14@e.com", name="Owner14")
    member = User.objects.create_user(email="member14@e.com", name="Member14")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.get(f"/api/me/payments/?group={g.id}&year=abc")
    assert r.status_code == 400
    assert r.json()["detail"] == "year and month must be integers."


@pytest.mark.django_db
def test_notification_body_contains_payer_name_not_email(api_client):
    """Notification body for payment_submitted uses payer's display name, not their email."""
    owner = User.objects.create_user(email="owner15@e.com", name="OwnerFifteen")
    member = User.objects.create_user(email="member15@e.com", name="MemberFifteen")
    g = make_group(owner, member)

    auth(api_client, member)
    r = api_client.post(
        f"/api/groups/{g.id}/payments/",
        {"amount": "750.00", "year": 2026, "month": 6},
        format="json",
    )
    assert r.status_code == 201

    notif = Notification.objects.get(user=owner, type="payment_submitted")
    assert "MemberFifteen" in notif.body
    assert "member15@e.com" not in notif.body
