import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

@pytest.mark.django_db
def test_create_user_with_email():
    u = User.objects.create_user(email="a@b.com", name="Ali")
    assert u.email == "a@b.com"
    assert u.name == "Ali"
    assert u.email_verified is False
    assert u.has_usable_password() is False

@pytest.mark.django_db
def test_email_is_normalized_and_unique():
    User.objects.create_user(email="A@B.com")
    with pytest.raises(Exception):
        User.objects.create_user(email="a@b.com")
