from django.urls import path

from . import views

urlpatterns = [
    path("groups/<uuid:pk>/payments/", views.payments),
    path("me/payments/", views.my_payments),
    path("payments/<uuid:payment_id>/approve/", views.approve_payment),
    path("payments/<uuid:payment_id>/reject/", views.reject_payment),
]
