from django.urls import path
from . import views

urlpatterns = [
    path("groups/<uuid:pk>/haazri/summary/", views.haazri_summary),
    path("groups/<uuid:pk>/haazri/disputes/", views.list_disputes),
    path("groups/<uuid:pk>/haazri/", views.haazri),
    path("me/haazri/", views.my_haazri),
    path("haazri/attendance/<uuid:attendance_id>/dispute/", views.dispute_attendance),
    path("haazri/disputes/<uuid:dispute_id>/resolve/", views.resolve_dispute),
    path("haazri/<uuid:event_id>/attendance/", views.set_attendance),
    path("haazri/<uuid:event_id>/extras/", views.add_extra),
    path("haazri/<uuid:event_id>/", views.event_detail),
]
