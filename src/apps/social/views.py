from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.serializers import UserSerializer
from .models import Friendship, Group, GroupMembership
from .permissions import group_role, is_member, is_group_admin, is_owner
from .serializers import FriendRequestCreateSerializer, GroupCreateSerializer, MembershipSerializer

User = get_user_model()


def models_q(user):
    return Q(user_low=user) | Q(user_high=user)


def _req_payload(f, me):
    other = f.other(me)
    return {
        "id": str(f.id),
        "user": UserSerializer(other).data,
        "direction": "outgoing" if f.requested_by_id == me.id else "incoming",
        "created_at": f.created_at,
    }


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def send_friend_request(request):
    s = FriendRequestCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    email = s.validated_data["email"].lower()
    target = User.objects.filter(email=email).first()
    if target is None:
        return Response({"detail": "No Kharchay user with that email."}, status=400)
    if target.id == request.user.id:
        return Response({"detail": "You cannot friend yourself."}, status=400)
    if Friendship.between(request.user, target):
        return Response({"detail": "A friendship or request already exists."}, status=400)
    low, high = Friendship.ordered(request.user, target)
    try:
        f = Friendship.objects.create(user_low=low, user_high=high, requested_by=request.user)
    except IntegrityError:
        return Response({"detail": "A friendship or request already exists."}, status=400)
    return Response(_req_payload(f, request.user), status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_friend_requests(request):
    direction = request.query_params.get("direction", "incoming")
    base = Friendship.objects.filter(status=Friendship.PENDING).select_related(
        "user_low", "user_high", "requested_by"
    ).order_by("-created_at")
    if direction == "outgoing":
        qs = base.filter(requested_by=request.user)
    else:
        qs = base.filter(models_q(request.user)).exclude(requested_by=request.user)
    return Response([_req_payload(f, request.user) for f in qs])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_friend_request(request, pk, action):
    f = Friendship.objects.filter(pk=pk, status=Friendship.PENDING).filter(models_q(request.user)).first()
    if f is None:
        return Response({"detail": "Request not found."}, status=404)
    if f.requested_by_id == request.user.id:
        return Response({"detail": "You cannot respond to your own request."}, status=403)
    if action == "accept":
        f.status = Friendship.ACCEPTED
        f.responded_at = timezone.now()
        f.save(update_fields=["status", "responded_at"])
        return Response({"detail": "accepted"})
    if action == "reject":
        f.delete()
        return Response({"detail": "rejected"})
    return Response({"detail": "Invalid action."}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_friends(request):
    qs = Friendship.objects.filter(status=Friendship.ACCEPTED).filter(
        models_q(request.user)
    ).select_related("user_low", "user_high")
    friends = sorted((f.other(request.user) for f in qs), key=lambda u: (u.name or "").lower())
    return Response(UserSerializer(friends, many=True).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def groups(request):
    if request.method == "POST":
        s = GroupCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        g = Group.objects.create(name=s.validated_data["name"], owner=request.user)
        GroupMembership.objects.create(
            group=g, user=request.user, role=GroupMembership.OWNER,
            status=GroupMembership.ACTIVE, joined_at=timezone.now(),
        )
        return Response({"id": str(g.id), "name": g.name, "my_role": GroupMembership.OWNER, "member_count": 1}, status=201)
    mine = (
        GroupMembership.objects
        .filter(user=request.user, status=GroupMembership.ACTIVE)
        .select_related("group")
        .annotate(active_count=Count(
            "group__memberships",
            filter=Q(group__memberships__status=GroupMembership.ACTIVE),
        ))
    )
    return Response([
        {"id": str(m.group.id), "name": m.group.name, "my_role": m.role, "member_count": m.active_count}
        for m in mine
    ])


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_detail(request, pk):
    g = Group.objects.filter(pk=pk).first()
    role = group_role(request.user, g) if g else None
    if g is None or role is None:
        return Response({"detail": "Not found."}, status=404)
    members = list(
        GroupMembership.objects.filter(group=g, status=GroupMembership.ACTIVE).select_related("user")
    )
    return Response({
        "id": str(g.id),
        "name": g.name,
        "my_role": role,
        "member_count": len(members),
        "members": MembershipSerializer(members, many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def invite_to_group(request, pk):
    g = Group.objects.filter(pk=pk).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can invite."}, status=403)
    email = (request.data.get("email") or "").lower()
    target = User.objects.filter(email=email).first()
    if target is None:
        return Response({"detail": "No Kharchay user with that email."}, status=400)
    if not Friendship.are_friends(request.user, target):
        return Response({"detail": "You can only invite your friends."}, status=400)
    existing = GroupMembership.objects.filter(group=g, user=target).first()
    if existing and existing.status in (GroupMembership.INVITED, GroupMembership.ACTIVE):
        return Response({"detail": "Already invited or a member."}, status=400)
    if existing:  # previously left -> re-invite
        existing.status = GroupMembership.INVITED
        existing.invited_by = request.user
        existing.save(update_fields=["status", "invited_by"])
        m = existing
    else:
        m = GroupMembership.objects.create(
            group=g, user=target, role=GroupMembership.MEMBER,
            status=GroupMembership.INVITED, invited_by=request.user,
        )
    return Response({"id": str(m.id), "detail": "invited"}, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_invites(request):
    qs = GroupMembership.objects.filter(user=request.user, status=GroupMembership.INVITED).select_related("group", "invited_by").order_by("-created_at")
    return Response([
        {
            "id": str(m.id),
            "group": {"id": str(m.group_id), "name": m.group.name},
            "invited_by": UserSerializer(m.invited_by).data if m.invited_by else None,
        } for m in qs
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def respond_invite(request, pk, action):
    m = GroupMembership.objects.filter(pk=pk, user=request.user, status=GroupMembership.INVITED).first()
    if m is None:
        return Response({"detail": "Invite not found."}, status=404)
    if action == "accept":
        m.status = GroupMembership.ACTIVE
        m.joined_at = timezone.now()
        m.save(update_fields=["status", "joined_at"])
        return Response({"detail": "accepted"})
    if action == "reject":
        m.status = GroupMembership.LEFT
        m.save(update_fields=["status"])
        return Response({"detail": "rejected"})
    return Response({"detail": "Unknown action."}, status=400)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def set_member_role(request, pk, user_id):
    g = Group.objects.filter(pk=pk).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)
    if not is_owner(request.user, g):
        return Response({"detail": "Only the owner can change roles."}, status=403)
    m = GroupMembership.objects.filter(group=g, user_id=user_id, status=GroupMembership.ACTIVE).first()
    if m is None:
        return Response({"detail": "Member not found."}, status=404)
    if m.role == GroupMembership.OWNER:
        return Response({"detail": "Cannot change the owner's role."}, status=400)
    role = request.data.get("role")
    if role not in (GroupMembership.ADMIN, GroupMembership.MEMBER):
        return Response({"detail": "Invalid role."}, status=400)
    m.role = role
    m.save(update_fields=["role"])
    return Response({"detail": "updated", "role": role})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_member(request, pk, user_id):
    g = Group.objects.filter(pk=pk).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)
    m = GroupMembership.objects.filter(group=g, user_id=user_id, status=GroupMembership.ACTIVE).first()
    if m is None:
        return Response({"detail": "Member not found."}, status=404)
    if m.role == GroupMembership.OWNER:
        return Response({"detail": "The owner cannot be removed."}, status=400)
    is_self = str(user_id) == str(request.user.id)
    if not (is_self or is_group_admin(request.user, g)):
        return Response({"detail": "Only admins can remove members."}, status=403)
    m.status = GroupMembership.LEFT
    m.save(update_fields=["status"])
    return Response({"detail": "removed"})
