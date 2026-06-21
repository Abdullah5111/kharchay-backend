import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.social.models import Group, GroupMembership
from apps.payments.models import Payment
from apps.payments import storage

User = get_user_model()


def make_group(owner, *members):
    g = Group.objects.create(name="House 8", owner=owner)
    GroupMembership.objects.create(group=g, user=owner, role="owner", status="active")
    for m in members:
        GroupMembership.objects.create(group=g, user=m, role="member", status="active")
    return g


@pytest.mark.django_db
def test_payment_defaults_to_submitted():
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    p = Payment.objects.create(group=g, user=a, year=2026, month=6, amount=Decimal("500.00"))
    assert p.status == "submitted"
    assert p.proof_image == ""


@pytest.mark.django_db
def test_save_proof_stores_key(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    a = User.objects.create_user(email="a@e.com", name="A")
    g = make_group(a)
    f = SimpleUploadedFile("p.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, content_type="image/png")
    storage.validate_image(f)
    key = storage.save_proof(g.id, f)
    assert key.startswith(f"proofs/{g.id}/")
    assert key.endswith(".png")


def test_validate_image_rejects_bad_type():
    f = SimpleUploadedFile("p.txt", b"hello", content_type="text/plain")
    with pytest.raises(ValueError):
        storage.validate_image(f)
