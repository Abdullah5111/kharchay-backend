import pytest
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import DeviceToken

User = get_user_model()

@pytest.mark.django_db
def test_register_device_upserts(api_client):
    u = User.objects.create_user(email="d@e.com")
    token = RefreshToken.for_user(u).access_token
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    for _ in range(2):
        resp = api_client.post("/api/devices/",
            {"expo_push_token": "ExponentPushToken[abc]", "platform": "android"},
            format="json")
        assert resp.status_code == 200
    assert DeviceToken.objects.filter(expo_push_token="ExponentPushToken[abc]").count() == 1
