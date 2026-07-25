"""Throttle classes for the OTP endpoints.

The default DRF ``get_ident`` trusts ``X-Forwarded-For`` when ``NUM_PROXIES``
is unset, and XFF is client-supplied — an attacker can send a fresh forged XFF
per request to land in a new throttle bucket every time, defeating the OTP
rate limits entirely.

The app is only reachable through Cloudflare Tunnel (containers bind to
127.0.0.1, no public ports), so ``CF-Connecting-IP`` is set by the Cloudflare
edge and overwrites any client-supplied value — it cannot be spoofed. We key
the IP throttles on that header (falling back to ``REMOTE_ADDR``) and never
trust XFF. We also cap OTP requests per-email so a single inbox can't be
bombed from rotating IPs.
"""
from rest_framework.throttling import SimpleRateThrottle


def trusted_client_ip(request) -> str:
    """Client identity we can trust for rate-limiting.

    Prefers Cloudflare's ``CF-Connecting-IP`` (un-spoofable given tunnel-only
    ingress); falls back to ``REMOTE_ADDR``. Deliberately ignores
    ``X-Forwarded-For``, which the client can forge.
    """
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip.strip()
    return request.META.get("REMOTE_ADDR", "") or ""


class _TrustedIPThrottle(SimpleRateThrottle):
    """Rate-limit keyed on a trusted client IP rather than raw XFF."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": trusted_client_ip(request)}


class OTPRequestThrottle(_TrustedIPThrottle):
    scope = "otp"


class OTPVerifyThrottle(_TrustedIPThrottle):
    scope = "otp_verify"


class LoginThrottle(_TrustedIPThrottle):
    """Rate-limit password-login attempts per trusted client IP to blunt
    brute-force guessing."""

    scope = "login"


class OTPEmailThrottle(SimpleRateThrottle):
    """Per-email cap on OTP requests — independent of source IP, so rotating
    IPs can't be used to bomb one victim's inbox."""

    scope = "otp_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") or ""
        email = email.strip().lower() if isinstance(email, str) else ""
        if not email:
            return None  # nothing to key on; the IP throttle still applies
        return self.cache_format % {"scope": self.scope, "ident": email}
