import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

@pytest.mark.django_db
def test_create_group_makes_owner_membership(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    auth(api_client, a)
    r = api_client.post("/api/groups/", {"name": "House 8"}, format="json")
    assert r.status_code == 201
    gid = r.json()["id"]
    listing = api_client.get("/api/groups/").json()
    assert len(listing) == 1
    assert listing[0]["my_role"] == "owner"
    assert listing[0]["member_count"] == 1
    detail = api_client.get(f"/api/groups/{gid}/").json()
    assert detail["members"][0]["role"] == "owner"
    assert detail["members"][0]["user"]["email"] == "a@e.com"

@pytest.mark.django_db
def test_non_member_cannot_view_group(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    auth(api_client, b)
    assert api_client.get(f"/api/groups/{gid}/").status_code == 404
    assert api_client.get("/api/groups/").json() == []
