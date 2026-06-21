from django.urls import path
from . import views

urlpatterns = [
    path("friends/", views.list_friends),
    path("friends/requests/", views.send_friend_request),
    path("friends/requests/list/", views.list_friend_requests),
    path("friends/requests/<uuid:pk>/accept/", views.respond_friend_request, {"action": "accept"}),
    path("friends/requests/<uuid:pk>/reject/", views.respond_friend_request, {"action": "reject"}),
    path("groups/", views.groups),
    path("groups/<uuid:pk>/", views.group_detail),
    path("groups/<uuid:pk>/invite/", views.invite_to_group),
    path("invites/", views.my_invites),
    path("invites/<uuid:pk>/accept/", views.respond_invite, {"action": "accept"}),
    path("invites/<uuid:pk>/reject/", views.respond_invite, {"action": "reject"}),
    path("groups/<uuid:pk>/members/<uuid:user_id>/role/", views.set_member_role),
    path("groups/<uuid:pk>/members/<uuid:user_id>/", views.remove_member),
]
