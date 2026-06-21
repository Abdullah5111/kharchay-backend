from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from . import otp
from .serializers import RequestOTPSerializer, VerifyOTPSerializer, UserSerializer, DeviceSerializer
from .models import DeviceToken
from .tasks import send_otp_email

User = get_user_model()


class OTPThrottle(ScopedRateThrottle):
    scope = "otp"


class OTPVerifyThrottle(ScopedRateThrottle):
    scope = "otp_verify"


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPThrottle])
def request_otp(request):
    s = RequestOTPSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    email = s.validated_data["email"]
    code = otp.issue_otp(email, s.validated_data["purpose"])
    send_otp_email.delay(email, code)
    return Response({"detail": "OTP sent"}, status=status.HTTP_202_ACCEPTED)

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPVerifyThrottle])
def verify_otp(request):
    s = VerifyOTPSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    email = s.validated_data["email"].lower()
    if not otp.verify_otp(email, s.validated_data["code"], s.validated_data["purpose"]):
        return Response({"detail": "Invalid or expired code"}, status=status.HTTP_400_BAD_REQUEST)
    user, is_new = User.objects.get_or_create(email=email)
    if not user.email_verified:
        user.email_verified = True
        user.save(update_fields=["email_verified"])
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
        "is_new": is_new,
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_device(request):
    s = DeviceSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    DeviceToken.objects.update_or_create(
        expo_push_token=s.validated_data["expo_push_token"],
        defaults={"user": request.user, "platform": s.validated_data["platform"]},
    )
    return Response({"detail": "registered"})

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        request.user.name = s.validated_data.get("name", request.user.name)
        request.user.save(update_fields=["name"])
    return Response(UserSerializer(request.user).data)
