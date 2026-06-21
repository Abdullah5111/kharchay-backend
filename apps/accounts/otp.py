import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import F
from django.utils import timezone
from .models import EmailOTP

def issue_otp(email: str, purpose: str = "login") -> str:
    email = email.lower()
    code = f"{secrets.randbelow(1_000_000):06d}"
    EmailOTP.objects.filter(email=email, consumed_at__isnull=True).delete()
    EmailOTP.objects.create(
        email=email,
        code_hash=make_password(code),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS),
    )
    return code

def verify_otp(email: str, code: str, purpose: str = "login") -> bool:
    email = email.lower()
    rec = (EmailOTP.objects
           .filter(email=email, consumed_at__isnull=True)
           .order_by("-created_at").first())
    if rec is None:
        return False
    if rec.attempts >= settings.OTP_MAX_ATTEMPTS or rec.expires_at < timezone.now():
        return False
    if not check_password(code, rec.code_hash):
        EmailOTP.objects.filter(pk=rec.pk).update(attempts=F("attempts") + 1)
        return False
    rec.consumed_at = timezone.now()
    rec.save(update_fields=["consumed_at"])
    return True
