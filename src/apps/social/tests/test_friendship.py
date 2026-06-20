import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

@pytest.mark.django_db
def test_send_and_accept_friend_request(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    r = api_client.post("/api/friends/requests/", {"email": "b@e.com"}, format="json")
    assert r.status_code == 201
    req_id = r.json()["id"]
    # b accepts
    auth(api_client, b)
    assert api_client.post(f"/api/friends/requests/{req_id}/accept/").status_code == 200
    # both now see each other as friends
    assert api_client.get("/api/friends/").json()[0]["email"] == "a@e.com"

@pytest.mark.django_db
def test_cannot_friend_self_or_duplicate(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    assert api_client.post("/api/friends/requests/", {"email": "a@e.com"}, format="json").status_code == 400
    assert api_client.post("/api/friends/requests/", {"email": "b@e.com"}, format="json").status_code == 201
    assert api_client.post("/api/friends/requests/", {"email": "b@e.com"}, format="json").status_code == 400

@pytest.mark.django_db
def test_only_recipient_can_accept(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    req_id = api_client.post("/api/friends/requests/", {"email": "b@e.com"}, format="json").json()["id"]
    # requester cannot accept their own request
    assert api_client.post(f"/api/friends/requests/{req_id}/accept/").status_code in (403, 404)

@pytest.mark.django_db
def test_reverse_direction_duplicate_request_returns_400(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    assert api_client.post("/api/friends/requests/", {"email": "b@e.com"}, format="json").status_code == 201
    # b tries to send a request back to a while one already exists -> 400, not 500
    auth(api_client, b)
    assert api_client.post("/api/friends/requests/", {"email": "a@e.com"}, format="json").status_code == 400
