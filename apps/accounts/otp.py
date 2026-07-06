import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.db import transaction
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
    # Lock the OTP row for the whole read-check-write so concurrent requests
    # serialize: without this, N simultaneous wrong guesses all read attempts
    # below the cap before any increment lands (defeating OTP_MAX_ATTEMPTS), and
    # two simultaneous correct submissions both consume the code and mint tokens.
    # select_for_update is a no-op on sqlite (dev/tests) but a real row lock on
    # Postgres (prod); mirrors the ledger's finalize-under-lock pattern.
    with transaction.atomic():
        rec = (EmailOTP.objects
               .select_for_update()
               .filter(email=email, consumed_at__isnull=True)
               .order_by("-created_at").first())
        if rec is None:
            return False
        if rec.attempts >= settings.OTP_MAX_ATTEMPTS or rec.expires_at < timezone.now():
            return False
        if not check_password(code, rec.code_hash):
            rec.attempts = F("attempts") + 1
            rec.save(update_fields=["attempts"])
            return False
        rec.consumed_at = timezone.now()
        rec.save(update_fields=["consumed_at"])
        return True
