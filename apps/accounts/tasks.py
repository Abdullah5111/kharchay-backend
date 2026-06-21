from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_otp_email(email: str, code: str):
    send_mail(
        subject="Your Kharchay code",
        message=f"Your Kharchay verification code is {code}. It expires in {settings.OTP_TTL_SECONDS // 60} minutes.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
