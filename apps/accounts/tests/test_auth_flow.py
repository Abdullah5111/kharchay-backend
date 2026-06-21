import pytest
from django.contrib.auth import get_user_model
from apps.accounts import otp

User = get_user_model()

@pytest.mark.django_db
def test_verify_otp_creates_user_and_returns_tokens(api_client):
    code = otp.issue_otp("new@user.com", "signup")
    resp = api_client.post("/api/auth/verify-otp/",
        {"email": "new@user.com", "code": code, "purpose": "signup"}, format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new"] is True
    assert body["user"]["email"] == "new@user.com"
    assert body["user"]["email_verified"] is True
    assert "access" in body and "refresh" in body
    assert User.objects.filter(email="new@user.com").count() == 1

@pytest.mark.django_db
def test_verify_otp_existing_user_is_not_new(api_client):
    User.objects.create_user(email="old@user.com", name="Old")
    code = otp.issue_otp("old@user.com", "login")
    resp = api_client.post("/api/auth/verify-otp/",
        {"email": "old@user.com", "code": code}, format="json")
    assert resp.status_code == 200
    assert resp.json()["is_new"] is False

@pytest.mark.django_db
def test_verify_otp_bad_code_rejected(api_client):
    otp.issue_otp("z@z.com", "login")
    resp = api_client.post("/api/auth/verify-otp/",
        {"email": "z@z.com", "code": "999999"}, format="json")
    assert resp.status_code == 400
