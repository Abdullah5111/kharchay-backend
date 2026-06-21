import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def auth(client, user):
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

@pytest.mark.django_db
def test_get_me_requires_auth(api_client):
    assert api_client.get("/api/me/").status_code == 401

@pytest.mark.django_db
def test_get_and_patch_me(api_client):
    u = User.objects.create_user(email="m@e.com", name="Initial")
    auth(api_client, u)
    assert api_client.get("/api/me/").json()["name"] == "Initial"
    resp = api_client.patch("/api/me/", {"name": "Updated"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"
    u.refresh_from_db()
    assert u.name == "Updated"


@pytest.mark.django_db
def test_patch_me_requires_auth(api_client):
    assert api_client.patch("/api/me/", {"name": "X"}, format="json").status_code == 401


@pytest.mark.django_db
def test_patch_me_cannot_overwrite_email(api_client):
    u = User.objects.create_user(email="orig@e.com", name="N")
    auth(api_client, u)
    resp = api_client.patch("/api/me/", {"email": "evil@e.com", "name": "N"}, format="json")
    assert resp.status_code == 200
    u.refresh_from_db()
    assert u.email == "orig@e.com"

