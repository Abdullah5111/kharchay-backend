import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.notifications.models import Notification
from apps.notifications.services import notify

User = get_user_model()

def auth(c, u): c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(u).access_token}")

@pytest.mark.django_db
def test_notify_creates_rows_and_lists(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    notify([a, b], "meal_marked", "Lunch", "You were marked for Lunch", {"x": 1})
    assert Notification.objects.filter(user=a).count() == 1
    auth(api_client, a)
    data = api_client.get("/api/notifications/").json()
    assert data[0]["title"] == "Lunch"
    assert data[0]["read"] is False
    assert api_client.get("/api/notifications/unread-count/").json()["count"] == 1

@pytest.mark.django_db
def test_mark_read(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    notify([a], "x", "t", "b")
    auth(api_client, a)
    assert api_client.post("/api/notifications/read/", {}, format="json").status_code == 200
    assert api_client.get("/api/notifications/unread-count/").json()["count"] == 0

@pytest.mark.django_db
def test_only_my_notifications(api_client):
    a = User.objects.create_user(email="a@e.com", name="A")
    b = User.objects.create_user(email="b@e.com", name="B")
    notify([b], "x", "t", "b")
    auth(api_client, a)
    assert api_client.get("/api/notifications/").json() == []
