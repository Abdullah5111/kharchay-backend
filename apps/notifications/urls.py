from django.urls import path
from . import views

urlpatterns = [
    path("notifications/", views.notifications),
    path("notifications/unread-count/", views.unread_count),
    path("notifications/read/", views.mark_read),
]
