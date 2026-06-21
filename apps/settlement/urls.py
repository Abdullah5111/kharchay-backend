from django.urls import path
from . import views

urlpatterns = [
    path("groups/<uuid:pk>/settlement/", views.settlement_preview, name="settlement_preview"),
    path("groups/<uuid:pk>/settlement/<int:year>/<int:month>/generate/", views.generate_settlement, name="generate_settlement"),
    path("me/standing/", views.my_standing, name="my_standing"),
    path("me/activity/", views.my_activity, name="my_activity"),
]
