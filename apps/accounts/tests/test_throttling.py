"""Throttle-identity tests for the OTP endpoints.

These pin down the fix for the X-Forwarded-For bypass: throttle buckets must be
keyed on an identity the client cannot forge (Cloudflare's CF-Connecting-IP,
falling back to REMOTE_ADDR), and OTP requests must additionally be capped
per-email so one inbox can't be bombed from rotating IPs.
"""
import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _throttle_env(settings):
    # Run the OTP email task inline (no broker) and start every test with an
    # empty throttle cache so counters don't leak across tests.
    settings.CELERY_TASK_ALWAYS_EAGER = True
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_forged_xff_cannot_rotate_ip_throttle_bucket(api_client):
    # Same real client, rotating a *forged* X-Forwarded-For on each request.
    # Distinct emails so the per-email cap can't be what fires — this isolates
    # the IP throttle (otp: 5/hour), which must ignore XFF and block the 6th.
    codes = []
    for i in range(6):
        r = api_client.post(
            "/api/auth/request-otp/",
            {"email": f"u{i}@e.com"},
            format="json",
            HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",
        )
        codes.append(r.status_code)
    assert codes[:5] == [202] * 5
    assert codes[5] == 429


@pytest.mark.django_db
def test_per_email_cap_holds_across_rotating_ips(api_client):
    # One victim inbox, attacker rotating the (trusted) Cloudflare client IP.
    # The per-email cap (otp_email: 5/hour) must still fire on the 6th.
    codes = []
    for i in range(6):
        r = api_client.post(
            "/api/auth/request-otp/",
            {"email": "victim@e.com"},
            format="json",
            HTTP_CF_CONNECTING_IP=f"203.0.113.{i}",
        )
        codes.append(r.status_code)
    assert codes[:5] == [202] * 5
    assert codes[5] == 429


@pytest.mark.django_db
def test_distinct_clients_are_not_throttled(api_client):
    # Different real clients (distinct CF IPs) requesting for different emails
    # must all succeed — the fix must not throttle unrelated legitimate users.
    codes = []
    for i in range(6):
        r = api_client.post(
            "/api/auth/request-otp/",
            {"email": f"c{i}@e.com"},
            format="json",
            HTTP_CF_CONNECTING_IP=f"198.51.100.{i}",
        )
        codes.append(r.status_code)
    assert codes == [202] * 6
