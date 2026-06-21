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


@pytest.mark.django_db
def test_refresh_token_returns_new_access(api_client):
    code = otp.issue_otp("r@user.com", "login")
    tokens = api_client.post("/api/auth/verify-otp/",
        {"email": "r@user.com", "code": code}, format="json").json()
    # Exchange the refresh token for a fresh access token
    resp = api_client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert resp.status_code == 200
    new_access = resp.json()["access"]
    assert new_access
    # The new access token authenticates against a protected endpoint
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
    me = api_client.get("/api/me/")
    assert me.status_code == 200
    assert me.json()["email"] == "r@user.com"


@pytest.mark.django_db
def test_refresh_with_bad_token_rejected(api_client):
    resp = api_client.post("/api/auth/refresh/", {"refresh": "not-a-real-token"}, format="json")
    assert resp.status_code == 401
