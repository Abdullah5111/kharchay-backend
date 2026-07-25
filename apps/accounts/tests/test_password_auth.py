import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts import otp

User = get_user_model()


def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")


@pytest.mark.django_db
def test_login_with_password_succeeds(api_client):
    User.objects.create_user(email="p@e.com", name="P", password="s3cret-pass")
    resp = api_client.post("/api/auth/login/", {"email": "p@e.com", "password": "s3cret-pass"}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert "access" in body and "refresh" in body
    assert body["user"]["email"] == "p@e.com"
    assert body["has_password"] is True


@pytest.mark.django_db
def test_login_wrong_password_rejected(api_client):
    User.objects.create_user(email="p@e.com", name="P", password="s3cret-pass")
    resp = api_client.post("/api/auth/login/", {"email": "p@e.com", "password": "wrong"}, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_login_unknown_email_rejected(api_client):
    resp = api_client.post("/api/auth/login/", {"email": "nobody@e.com", "password": "x"}, format="json")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_login_without_usable_password_conflicts(api_client):
    # create_user with no password sets an unusable password (legacy OTP account)
    User.objects.create_user(email="np@e.com", name="NP")
    resp = api_client.post("/api/auth/login/", {"email": "np@e.com", "password": "anything"}, format="json")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "no_password"


@pytest.mark.django_db
def test_set_password_then_login(api_client):
    u = User.objects.create_user(email="np@e.com", name="NP")
    assert u.has_usable_password() is False
    auth(api_client, u)
    resp = api_client.post("/api/auth/set-password/", {"password": "brand-new-pw"}, format="json")
    assert resp.status_code == 200
    api_client.credentials()  # drop bearer; now log in with the password
    login = api_client.post("/api/auth/login/", {"email": "np@e.com", "password": "brand-new-pw"}, format="json")
    assert login.status_code == 200
    assert login.json()["has_password"] is True


@pytest.mark.django_db
def test_set_password_requires_auth(api_client):
    assert api_client.post("/api/auth/set-password/", {"password": "x2345678"}, format="json").status_code == 401


@pytest.mark.django_db
def test_set_password_enforces_min_length(api_client):
    u = User.objects.create_user(email="np@e.com", name="NP")
    auth(api_client, u)
    assert api_client.post("/api/auth/set-password/", {"password": "short"}, format="json").status_code == 400


@pytest.mark.django_db
def test_verify_otp_reports_has_password(api_client):
    # A fresh OTP signup has no usable password yet.
    code = otp.issue_otp("fresh@e.com", "signup")
    resp = api_client.post("/api/auth/verify-otp/",
        {"email": "fresh@e.com", "code": code, "purpose": "signup"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["has_password"] is False
