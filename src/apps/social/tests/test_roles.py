import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.social.models import Group, GroupMembership

User = get_user_model()

def auth(client, user):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

def setup_group_with_member(owner_email="a@e.com", member_email="b@e.com"):
    a = User.objects.create_user(email=owner_email, name="A")
    b = User.objects.create_user(email=member_email, name="B")
    g = Group.objects.create(name="House 8", owner=a)
    GroupMembership.objects.create(group=g, user=a, role="owner", status="active")
    GroupMembership.objects.create(group=g, user=b, role="member", status="active")
    return a, b, g

@pytest.mark.django_db
def test_owner_promotes_member_to_admin(api_client):
    a, b, g = setup_group_with_member()
    auth(api_client, a)
    r = api_client.post(f"/api/groups/{g.id}/members/{b.id}/role/", {"role": "admin"}, format="json")
    assert r.status_code == 200
    assert GroupMembership.objects.get(group=g, user=b).role == "admin"

@pytest.mark.django_db
def test_member_cannot_promote(api_client):
    a, b, g = setup_group_with_member()
    c = User.objects.create_user(email="c@e.com", name="C")
    GroupMembership.objects.create(group=g, user=c, role="member", status="active")
    auth(api_client, b)
    assert api_client.post(f"/api/groups/{g.id}/members/{c.id}/role/", {"role": "admin"}, format="json").status_code == 403

@pytest.mark.django_db
def test_admin_removes_member(api_client):
    a, b, g = setup_group_with_member()
    auth(api_client, a)
    assert api_client.delete(f"/api/groups/{g.id}/members/{b.id}/").status_code == 200
    assert GroupMembership.objects.get(group=g, user=b).status == "left"

@pytest.mark.django_db
def test_cannot_change_owner_role(api_client):
    a, b, g = setup_group_with_member()
    auth(api_client, a)
    assert api_client.post(f"/api/groups/{g.id}/members/{a.id}/role/", {"role": "member"}, format="json").status_code == 400


@pytest.mark.django_db
def test_admin_cannot_promote(api_client):
    a, b, g = setup_group_with_member()
    c = User.objects.create_user(email="c@e.com", name="C")
    GroupMembership.objects.create(group=g, user=c, role="member", status="active")
    GroupMembership.objects.filter(group=g, user=b).update(role="admin")  # b is now admin, still not owner
    auth(api_client, b)
    assert api_client.post(f"/api/groups/{g.id}/members/{c.id}/role/", {"role": "admin"}, format="json").status_code == 403


@pytest.mark.django_db
def test_non_member_gets_404_on_role_and_remove(api_client):
    a, b, g = setup_group_with_member()
    outsider = User.objects.create_user(email="out@e.com", name="O")
    auth(api_client, outsider)
    assert api_client.post(f"/api/groups/{g.id}/members/{b.id}/role/", {"role": "admin"}, format="json").status_code == 404
    assert api_client.delete(f"/api/groups/{g.id}/members/{b.id}/").status_code == 404


@pytest.mark.django_db
def test_invalid_role_rejected(api_client):
    a, b, g = setup_group_with_member()
    auth(api_client, a)
    assert api_client.post(f"/api/groups/{g.id}/members/{b.id}/role/", {"role": "superadmin"}, format="json").status_code == 400


@pytest.mark.django_db
def test_member_can_self_leave(api_client):
    a, b, g = setup_group_with_member()
    auth(api_client, b)
    assert api_client.delete(f"/api/groups/{g.id}/members/{b.id}/").status_code == 200
    assert GroupMembership.objects.get(group=g, user=b).status == "left"
