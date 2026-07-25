from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from . import otp
from .throttling import OTPRequestThrottle, OTPVerifyThrottle, OTPEmailThrottle, LoginThrottle
from .serializers import (
    RequestOTPSerializer,
    VerifyOTPSerializer,
    UserSerializer,
    DeviceSerializer,
    LoginSerializer,
    SetPasswordSerializer,
)
from .models import DeviceToken
from .tasks import send_otp_email

User = get_user_model()


def user_has_password(user) -> bool:
    """Whether the user has a real, usable password.

    ``has_usable_password()`` alone is not enough: users created via
    ``get_or_create`` (the OTP verify path) get ``password=""``, and Django
    treats an empty string as *usable* (it only checks the unusable prefix).
    Guard on a non-empty hash so empty/legacy accounts are correctly reported
    as password-less.
    """
    return bool(user.password) and user.has_usable_password()


def _token_response(user, **extra):
    """Issue a fresh JWT pair for ``user`` in the shape the app expects."""
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UserSerializer(user).data,
        **extra,
    })


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRequestThrottle, OTPEmailThrottle])
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
    # has_password tells the app whether to prompt the user to set one after a
    # code login (first-time users and legacy OTP accounts have no usable password).
    return _token_response(user, is_new=is_new, has_password=user_has_password(user))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginThrottle])
def login(request):
    s = LoginSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    email = s.validated_data["email"].lower()
    user = User.objects.filter(email=email).first()
    if user is None or not user.is_active:
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
    if not user_has_password(user):
        # Legacy/first-time account: guide the app to the email-code path.
        return Response(
            {"detail": "no_password", "hint": "Set a password via email code first."},
            status=status.HTTP_409_CONFLICT,
        )
    if not user.check_password(s.validated_data["password"]):
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
    return _token_response(user, has_password=True)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_password(request):
    s = SetPasswordSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    request.user.set_password(s.validated_data["password"])
    request.user.save(update_fields=["password"])
    return Response({"detail": "Password set."})

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
