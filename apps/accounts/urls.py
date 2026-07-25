from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path("auth/request-otp/", views.request_otp),
    path("auth/verify-otp/", views.verify_otp),
    path("auth/login/", views.login),
    path("auth/set-password/", views.set_password),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", views.me, name="me"),
    path("devices/", views.register_device),
]
