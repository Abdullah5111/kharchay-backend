from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.social.models import Group, GroupMembership
from apps.social.permissions import is_member, is_group_admin
from apps.ledger.models import Category
from apps.notifications.services import notify
from .models import MealEvent, MealAttendance, ExtraAmount, AttendanceDispute
from .serializers import (
    MealEventCreateSerializer, RosterSerializer, MealEventSerializer,
    MealEventDetailSerializer, ExtraCreateSerializer,
    AttendanceHistorySerializer, PoolSummarySerializer, PerUserUnitsSerializer,
    DisputeSerializer, DisputeCreateSerializer, DisputeResolveSerializer,
)

User = get_user_model()


def _group_or_404(request, pk):
    g = Group.objects.filter(pk=pk).first()
    return g if (g and is_member(request.user, g)) else None


def _load_event(event_id):
    return MealEvent.objects.select_related("category").prefetch_related(
        "attendance__user", "extras__paid_by"
    ).get(id=event_id)


def _active_member_ids(group):
    return set(str(uid) for uid in GroupMembership.objects.filter(
        group=group, status="active").values_list("user_id", flat=True))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def haazri(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if request.method == "POST":
        if not is_group_admin(request.user, g):
            return Response({"detail": "Only admins can mark Haazri."}, status=403)
        s = MealEventCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cat = Category.objects.filter(pk=s.validated_data["category"], group=g, ledger_type="kitchen_pool").first()
        if cat is None:
            return Response({"detail": "Invalid kitchen pool category."}, status=400)
        ev, created = MealEvent.objects.get_or_create(
            group=g, category=cat, date=s.validated_data["date"],
            defaults={"created_by": request.user, "note": s.validated_data["note"]})
        return Response(MealEventSerializer(_load_event(ev.id)).data, status=201 if created else 200)
    date = request.query_params.get("date")
    qs = MealEvent.objects.filter(group=g).select_related("category").prefetch_related(
        "attendance__user", "extras__paid_by"
    )
    if date:
        qs = qs.filter(date=date)
    return Response(MealEventSerializer(qs, many=True).data)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def set_attendance(request, event_id):
    ev = MealEvent.objects.select_related("group").filter(id=event_id).first()
    if ev is None or not is_member(request.user, ev.group):
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, ev.group):
        return Response({"detail": "Only admins can mark Haazri."}, status=403)
    s = RosterSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    member_ids = _active_member_ids(ev.group)
    entries = s.validated_data["entries"]
    if any(str(e["user"]) not in member_ids for e in entries):
        return Response({"detail": "All attendees must be active members."}, status=400)
    entry_ids = [str(e["user"]) for e in entries]
    if len(entry_ids) != len(set(entry_ids)):
        return Response({"detail": "A member appears more than once in the roster."}, status=400)
    previously = set(str(uid) for uid in ev.attendance.values_list("user_id", flat=True))
    with transaction.atomic():
        ev.attendance.all().delete()
        MealAttendance.objects.bulk_create([
            MealAttendance(meal_event=ev, user_id=e["user"], multiplier=e["multiplier"], guest_label=e["guest_label"])
            for e in entries])
    newly = [e["user"] for e in entries if str(e["user"]) not in previously]
    if newly:
        users = list(User.objects.filter(id__in=newly))
        label = ev.category.name
        notify(users, "meal_marked", label, f"You were marked for {label} on {ev.date}.",
               {"event_id": str(ev.id), "date": str(ev.date)})
    return Response(MealEventSerializer(_load_event(ev.id)).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def event_detail(request, event_id):
    ev = MealEvent.objects.select_related("group").filter(id=event_id).first()
    if ev is None or not is_member(request.user, ev.group):
        return Response({"detail": "Not found."}, status=404)
    return Response(MealEventDetailSerializer(_load_event(ev.id)).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_extra(request, event_id):
    ev = MealEvent.objects.select_related("group").filter(id=event_id).first()
    if ev is None or not is_member(request.user, ev.group):
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, ev.group):
        return Response({"detail": "Only admins can add extras."}, status=403)
    s = ExtraCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    member_ids = _active_member_ids(ev.group)
    if str(s.validated_data["paid_by"]) not in member_ids:
        return Response({"detail": "Payer must be an active member of the group."}, status=400)
    payer = User.objects.filter(id=s.validated_data["paid_by"]).first()
    if payer is None:
        return Response({"detail": "Payer not found."}, status=400)
    extra = ExtraAmount.objects.create(
        meal_event=ev,
        title=s.validated_data["title"],
        amount=s.validated_data["amount"],
        paid_by=payer,
        created_by=request.user,
    )
    # Reload with relations for serialization
    extra = ExtraAmount.objects.select_related("paid_by").get(id=extra.id)
    from .serializers import ExtraSerializer
    return Response(ExtraSerializer(extra).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def haazri_summary(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)

    year = request.query_params.get("year")
    month = request.query_params.get("month")
    if not year or not month:
        return Response({"detail": "year and month are required."}, status=400)
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return Response({"detail": "year and month must be integers."}, status=400)

    # Find all categories that have events for this group/year/month
    category_ids = MealEvent.objects.filter(
        group=g, date__year=year, date__month=month
    ).values_list("category_id", flat=True).distinct()

    categories = Category.objects.filter(id__in=category_ids)

    results = []
    for cat in categories:
        base_qs = MealAttendance.objects.filter(
            meal_event__group=g,
            meal_event__category=cat,
            meal_event__date__year=year,
            meal_event__date__month=month,
        )
        total_units = base_qs.aggregate(total=Sum("multiplier"))["total"] or 0
        extras_total = ExtraAmount.objects.filter(
            meal_event__group=g,
            meal_event__category=cat,
            meal_event__date__year=year,
            meal_event__date__month=month,
        ).aggregate(total=Sum("amount"))["total"] or 0

        per_user_qs = base_qs.values("user").annotate(units=Sum("multiplier"))
        user_ids = [row["user"] for row in per_user_qs]
        user_map = {u.id: u for u in User.objects.filter(id__in=user_ids)}

        per_user = [
            {"user": user_map[row["user"]], "units": row["units"]}
            for row in per_user_qs
            if row["user"] in user_map
        ]

        results.append({
            "category": cat.id,
            "category_name": cat.name,
            "total_units": total_units,
            "extras_total": extras_total,
            "per_user": per_user,
        })

    return Response(PoolSummarySerializer(results, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_haazri(request):
    group_id = request.query_params.get("group")
    year = request.query_params.get("year")
    month = request.query_params.get("month")

    if not group_id or not year or not month:
        return Response({"detail": "group, year, and month are required."}, status=400)
    try:
        year = int(year)
        month = int(month)
    except ValueError:
        return Response({"detail": "year and month must be integers."}, status=400)

    g = Group.objects.filter(pk=group_id).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)

    qs = MealAttendance.objects.filter(
        user=request.user,
        meal_event__group=g,
        meal_event__date__year=year,
        meal_event__date__month=month,
    ).select_related("meal_event__category", "user")

    return Response(AttendanceHistorySerializer(qs, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dispute_attendance(request, attendance_id):
    att = MealAttendance.objects.select_related("meal_event__group", "meal_event__category", "user").filter(
        id=attendance_id
    ).first()

    if att is None or att.user != request.user:
        return Response({"detail": "Not found."}, status=404)

    if not is_member(request.user, att.meal_event.group):
        return Response({"detail": "Not found."}, status=404)

    if AttendanceDispute.objects.filter(meal_event=att.meal_event, user=att.user, status="open").exists():
        return Response({"detail": "This attendance is already under dispute."}, status=400)

    s = DisputeCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)

    AttendanceDispute.objects.create(
        meal_event=att.meal_event,
        user=att.user,
        raised_by=request.user,
        reason=s.validated_data["reason"],
        status=AttendanceDispute.STATUS_OPEN,
    )

    # Notify group admins/owner
    admin_memberships = GroupMembership.objects.filter(
        group=att.meal_event.group,
        status="active",
        role__in=["owner", "admin"],
    ).select_related("user")
    admin_users = [m.user for m in admin_memberships]
    notify(
        admin_users,
        "attendance_disputed",
        "Attendance Disputed",
        f"{request.user} disputed their attendance for {att.meal_event.category.name} on {att.meal_event.date}.",
        {"meal_event_id": str(att.meal_event.id)},
    )

    return Response({"detail": "Dispute created."}, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_disputes(request, pk):
    g = Group.objects.filter(pk=pk).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can view disputes."}, status=403)

    disputes = AttendanceDispute.objects.filter(
        meal_event__group=g,
        status=AttendanceDispute.STATUS_OPEN,
    ).select_related("meal_event__category", "user", "raised_by")

    return Response(DisputeSerializer(disputes, many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resolve_dispute(request, dispute_id):
    dispute = AttendanceDispute.objects.select_related(
        "meal_event__group"
    ).filter(id=dispute_id).first()

    if dispute is None:
        return Response({"detail": "Not found."}, status=404)

    group = dispute.meal_event.group
    if not is_member(request.user, group):
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, group):
        return Response({"detail": "Only admins can resolve disputes."}, status=403)

    s = DisputeResolveSerializer(data=request.data)
    s.is_valid(raise_exception=True)

    action = s.validated_data["action"]
    dispute.status = AttendanceDispute.STATUS_RESOLVED if action == "resolve" else AttendanceDispute.STATUS_REJECTED
    dispute.resolved_by = request.user
    dispute.resolved_at = timezone.now()
    dispute.save()

    return Response(DisputeSerializer(dispute).data, status=200)
