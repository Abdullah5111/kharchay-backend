import pytest
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from apps.accounts import otp
from apps.accounts.models import EmailOTP

@pytest.mark.django_db
def test_issue_and_verify_success():
    code = otp.issue_otp("a@b.com", "login")
    assert len(code) == 6 and code.isdigit()
    assert otp.verify_otp("a@b.com", code, "login") is True

@pytest.mark.django_db
def test_wrong_code_fails_and_counts_attempt():
    code = otp.issue_otp("a@b.com", "login")
    wrong = "000000" if code != "000000" else "111111"
    assert otp.verify_otp("a@b.com", wrong, "login") is False
    rec = EmailOTP.objects.get(email="a@b.com")
    assert rec.attempts == 1

@pytest.mark.django_db
def test_expired_code_fails():
    code = otp.issue_otp("a@b.com", "login")
    EmailOTP.objects.filter(email="a@b.com").update(
        expires_at=timezone.now() - timedelta(seconds=1))
    assert otp.verify_otp("a@b.com", code, "login") is False

@pytest.mark.django_db
def test_request_otp_endpoint(api_client, settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    resp = api_client.post("/api/auth/request-otp/", {"email": "x@y.com"}, format="json")
    assert resp.status_code == 202
    assert EmailOTP.objects.filter(email="x@y.com").exists()

@pytest.mark.django_db
def test_attempts_cap_blocks_correct_code():
    code = otp.issue_otp("cap@e.com", "login")
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        assert otp.verify_otp("cap@e.com", wrong, "login") is False
    # even the correct code is now rejected once the cap is reached
    assert otp.verify_otp("cap@e.com", code, "login") is False

@pytest.mark.django_db
def test_reissue_invalidates_previous_code():
    first = otp.issue_otp("re@e.com", "login")
    otp.issue_otp("re@e.com", "login")  # second issue deletes the first unconsumed code
    assert otp.verify_otp("re@e.com", first, "login") is False
