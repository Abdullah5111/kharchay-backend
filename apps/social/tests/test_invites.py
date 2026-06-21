import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Friendship

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

def make_friends(a, b):
    low, high = Friendship.ordered(a, b)
    Friendship.objects.create(user_low=low, user_high=high, status=Friendship.ACCEPTED, requested_by=a)

@pytest.mark.django_db
def test_invite_friend_and_accept(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    make_friends(a, b)
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    assert api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json").status_code == 201
    # b sees the invite and accepts
    auth(api_client, b)
    invites = api_client.get("/api/invites/").json()
    assert len(invites) == 1
    mid = invites[0]["id"]
    assert api_client.post(f"/api/invites/{mid}/accept/").status_code == 200
    # b now an active member
    assert any(g["id"] == gid for g in api_client.get("/api/groups/").json())

@pytest.mark.django_db
def test_cannot_invite_non_friend(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    User.objects.create_user(email="b@e.com", name="B")
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    assert api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json").status_code == 400

@pytest.mark.django_db
def test_only_admin_can_invite(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    c = User.objects.create_user(email="c@e.com", name="C")
    make_friends(a, b); make_friends(b, c)
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json")
    auth(api_client, b)
    mid = api_client.get("/api/invites/").json()[0]["id"]
    api_client.post(f"/api/invites/{mid}/accept/")
    # b is a plain member, cannot invite c
    assert api_client.post(f"/api/groups/{gid}/invite/", {"email": "c@e.com"}, format="json").status_code == 403


@pytest.mark.django_db
def test_only_invitee_can_respond(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    c = User.objects.create_user(email="c@e.com", name="C")
    make_friends(a, b)
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json")
    auth(api_client, b)
    mid = api_client.get("/api/invites/").json()[0]["id"]
    # c (not the invitee) cannot accept b's invite
    auth(api_client, c)
    assert api_client.post(f"/api/invites/{mid}/accept/").status_code == 404


@pytest.mark.django_db
def test_reinvite_after_leaving(api_client):
    from apps.social.models import GroupMembership
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    make_friends(a, b)
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json")
    # b rejects -> membership status becomes "left"
    auth(api_client, b)
    mid = api_client.get("/api/invites/").json()[0]["id"]
    assert api_client.post(f"/api/invites/{mid}/reject/").status_code == 200
    # a re-invites b -> 201 and still exactly one membership row (no duplicate)
    auth(api_client, a)
    assert api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json").status_code == 201
    assert GroupMembership.objects.filter(group_id=gid, user=b).count() == 1


@pytest.mark.django_db
def test_cannot_invite_already_active_member(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    make_friends(a, b)
    auth(api_client, a)
    gid = api_client.post("/api/groups/", {"name": "House 8"}, format="json").json()["id"]
    api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json")
    auth(api_client, b)
    mid = api_client.get("/api/invites/").json()[0]["id"]
    api_client.post(f"/api/invites/{mid}/accept/")
    # a invites already-active b again -> 400
    auth(api_client, a)
    assert api_client.post(f"/api/groups/{gid}/invite/", {"email": "b@e.com"}, format="json").status_code == 400
