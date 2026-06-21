import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.social.models import Group
from apps.social.permissions import is_member, is_group_admin
from apps.ledger.models import LedgerPeriod, Expense
from apps.haazri.models import MealEvent, MealAttendance, ExtraAmount
from apps.notifications.services import notify
from apps.settlement.money import quantize, apportion

from .compute import compute_settlement
from .models import Settlement, SettlementLine, Transfer
from .serializers import LineOutSerializer, TransferOutSerializer, StandingSerializer, ActivityItemSerializer
from .transfers import minimize_transfers

LEDGER_TYPES = ["monthly_expense", "kitchen", "workplace"]


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _serialize_breakdown(breakdown):
    """Convert a breakdown dict (which may contain Decimal values) to a JSON-safe dict."""
    return json.loads(json.dumps(breakdown, cls=_DecimalEncoder))


def _group_or_404(request, pk):
    g = Group.objects.filter(pk=pk).first()
    return g if (g and is_member(request.user, g)) else None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def settlement_preview(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can view settlement preview."}, status=403)

    year = request.query_params.get("year")
    month = request.query_params.get("month")
    if not year or not month:
        return Response({"detail": "year and month are required."}, status=400)
    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return Response({"detail": "year and month must be integers."}, status=400)
    if not (1 <= month <= 12):
        return Response({"detail": "month must be between 1 and 12."}, status=status.HTTP_400_BAD_REQUEST)

    result = compute_settlement(g, year, month)

    nets = {uid: line["net"] for uid, line in result["lines"].items()}
    raw_transfers = minimize_transfers(nets)

    transfer_rows = []
    for t in raw_transfers:
        from_uid = t["from"]
        to_uid = t["to"]
        from_user = result["lines"][from_uid]["user"]
        to_user = result["lines"][to_uid]["user"]
        transfer_rows.append({"from_user": from_user, "to_user": to_user, "amount": t["amount"]})

    finalized = all(
        LedgerPeriod.status_for(g, lt, year, month) == "finalized"
        for lt in LEDGER_TYPES
    )

    lines_data = list(result["lines"].values())

    return Response({
        "year": year,
        "month": month,
        "finalized": finalized,
        "lines": LineOutSerializer(lines_data, many=True).data,
        "transfers": TransferOutSerializer(transfer_rows, many=True).data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_settlement(request, pk, year, month):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can generate settlement."}, status=403)
    if not (1 <= month <= 12):
        return Response({"detail": "month must be between 1 and 12."}, status=status.HTTP_400_BAD_REQUEST)

    not_finalized = [
        lt for lt in LEDGER_TYPES
        if LedgerPeriod.status_for(g, lt, year, month) != "finalized"
    ]
    if not_finalized:
        return Response(
            {"detail": "Finalize all ledgers before generating settlement."},
            status=400,
        )

    result = compute_settlement(g, year, month)
    nets = {uid: line["net"] for uid, line in result["lines"].items()}
    raw_transfers = minimize_transfers(nets)

    transfer_rows = []
    for t in raw_transfers:
        from_uid = t["from"]
        to_uid = t["to"]
        from_user = result["lines"][from_uid]["user"]
        to_user = result["lines"][to_uid]["user"]
        transfer_rows.append({"from_user": from_user, "to_user": to_user, "amount": t["amount"]})

    with transaction.atomic():
        Settlement.objects.filter(group=g, year=year, month=month).delete()
        settlement = Settlement.objects.create(
            group=g,
            year=year,
            month=month,
            status=Settlement.DRAFT,
            generated_by=request.user,
        )
        SettlementLine.objects.bulk_create([
            SettlementLine(
                settlement=settlement,
                user=line["user"],
                paid_total=line["paid_total"],
                owed_total=line["owed_total"],
                net=line["net"],
                breakdown=_serialize_breakdown(line["breakdown"]),
            )
            for line in result["lines"].values()
        ])
        Transfer.objects.bulk_create([
            Transfer(
                settlement=settlement,
                from_user=tr["from_user"],
                to_user=tr["to_user"],
                amount=tr["amount"],
            )
            for tr in transfer_rows
        ])

    # Notify all participants except the generator
    participants = result["participants"]
    recipients = [u for u in participants if u.id != request.user.id]
    if recipients:
        notify(
            recipients,
            "settlement_ready",
            "Settlement Ready",
            f"Settlement for {year}/{month:02d} has been generated.",
            {"settlement_id": str(settlement.id), "year": year, "month": month},
        )

    lines_data = list(result["lines"].values())

    return Response({
        "id": str(settlement.id),
        "status": settlement.status,
        "year": year,
        "month": month,
        "finalized": True,
        "lines": LineOutSerializer(lines_data, many=True).data,
        "transfers": TransferOutSerializer(transfer_rows, many=True).data,
    }, status=status.HTTP_201_CREATED)


def _validate_group_year_month(request):
    """Parse and validate group/year/month query params. Returns (group_id, year, month) or raises Response."""
    group_id = request.query_params.get("group")
    year = request.query_params.get("year")
    month = request.query_params.get("month")
    if not group_id:
        return None, None, None, Response({"detail": "group is required."}, status=400)
    if not year or not month:
        return None, None, None, Response({"detail": "year and month are required."}, status=400)
    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return None, None, None, Response({"detail": "year and month must be integers."}, status=400)
    if not (1 <= month <= 12):
        return None, None, None, Response({"detail": "month must be between 1 and 12."}, status=status.HTTP_400_BAD_REQUEST)
    return group_id, year, month, None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_standing(request):
    """GET /api/me/standing/?group=&year=&month=

    Returns the requesting user's settlement standing for a given group and month.
    Any active member can call this; only their own data is returned.
    """
    group_id, year, month, err = _validate_group_year_month(request)
    if err:
        return err

    g = Group.objects.filter(pk=group_id).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)

    result = compute_settlement(g, year, month)
    user_line = result["lines"].get(request.user.id)

    # Build all transfers, then filter to only those involving request.user
    nets = {uid: line["net"] for uid, line in result["lines"].items()}
    raw_transfers = minimize_transfers(nets)

    user_transfers = []
    for t in raw_transfers:
        from_uid = t["from"]
        to_uid = t["to"]
        if from_uid != request.user.id and to_uid != request.user.id:
            continue
        from_user = result["lines"][from_uid]["user"]
        to_user = result["lines"][to_uid]["user"]
        user_transfers.append({"from_user": from_user, "to_user": to_user, "amount": t["amount"]})

    # Look up persisted settlement status
    persisted = Settlement.objects.filter(group=g, year=year, month=month).first()
    settlement_status = persisted.status if persisted else "none"

    if user_line is None:
        # User has no activity in this month — return zeros
        data = {
            "paid_total": Decimal("0.00"),
            "owed_total": Decimal("0.00"),
            "net": Decimal("0.00"),
            "breakdown": {"non_kitchen": [], "kitchen": [], "extras": [], "paid": []},
            "transfers": [],
            "settlement_status": settlement_status,
        }
    else:
        data = {
            "paid_total": user_line["paid_total"],
            "owed_total": user_line["owed_total"],
            "net": user_line["net"],
            "breakdown": _serialize_breakdown(user_line["breakdown"]),
            "transfers": user_transfers,
            "settlement_status": settlement_status,
        }

    return Response(StandingSerializer(data).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_activity(request):
    """GET /api/me/activity/?group=&year=&month=

    Returns a flat, date-descending list of the requesting user's activity items
    for a given group and month. Items are either expenses (kind="expense") or
    meal events (kind="meal").

    Expense amount: the user's ExpenseShare.amount for that expense, or "0.00" if they
    appear only as payer with no share record.

    Meal amount: the user's proportional share of the event's total ExtraAmount(s),
    apportioned by attendance multiplier (last attendee absorbs rounding remainder).
    If the event has no ExtraAmount records, amount = "0.00".
    """
    group_id, year, month, err = _validate_group_year_month(request)
    if err:
        return err

    g = Group.objects.filter(pk=group_id).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)

    items = []

    # --- Expenses: user is paid_by OR holds a share ---
    expenses = (
        Expense.objects
        .filter(group=g, date__year=year, date__month=month)
        .filter(Q(paid_by=request.user) | Q(shares__user=request.user))
        .select_related("category", "paid_by")
        .prefetch_related("shares__user")
        .distinct()
    )

    for e in expenses:
        # Find the user's share amount
        share_amount = Decimal("0.00")
        for s in e.shares.all():
            if s.user_id == request.user.id:
                share_amount = s.amount
                break

        role = "payer" if e.paid_by_id == request.user.id else "participant"
        items.append({
            "kind": "expense",
            "date": e.date.isoformat(),
            "title": e.title or e.category.name,
            "ledger_type": e.ledger_type,
            "amount": str(share_amount),
            "role": role,
        })

    # --- Meal events: user attended ---
    meal_events = (
        MealEvent.objects
        .filter(group=g, date__year=year, date__month=month, attendance__user=request.user)
        .select_related("category")
        .prefetch_related("attendance__user", "extras__paid_by")
        .distinct()
    )

    for ev in meal_events:
        # Compute user's extras share for this event, mirroring compute.py:
        # apportion EACH ExtraAmount separately and accumulate the user's share.
        att_list = list(ev.attendance.all())
        extras_list = list(ev.extras.all())

        meal_amount = Decimal("0.00")
        if extras_list and att_list:
            # Materialize attendee list once; find the requesting user's index in that same list.
            user_idx = None
            for i, a in enumerate(att_list):
                if a.user_id == request.user.id:
                    user_idx = i
                    break

            if user_idx is not None:
                weights = [Decimal(a.multiplier) for a in att_list]
                for ex in extras_list:
                    shares = apportion(ex.amount, weights)
                    meal_amount += shares[user_idx]

        items.append({
            "kind": "meal",
            "date": ev.date.isoformat(),
            "title": ev.category.name,
            "pool_name": ev.category.name,
            "amount": str(meal_amount),
            "role": "participant",
        })

    # Sort by date descending
    items.sort(key=lambda x: x["date"], reverse=True)

    return Response(ActivityItemSerializer(items, many=True).data)
