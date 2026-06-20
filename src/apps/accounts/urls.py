from django.urls import path
from . import views

urlpatterns = [
    path("auth/request-otp/", views.request_otp),
    path("auth/verify-otp/", views.verify_otp),
    path("me/", views.me, name="me"),
    path("devices/", views.register_device),
]
