from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.social.models import Group, GroupMembership
from apps.social.permissions import is_member, is_group_admin
from .models import Category, Expense, ExpenseShare, LedgerPeriod
from .serializers import CategorySerializer, CategoryCreateSerializer, ExpenseCreateSerializer, ExpenseSerializer
from .constants import CATEGORY_KINDS
from . import splits

User = get_user_model()


def _group_or_404(request, pk):
    g = Group.objects.filter(pk=pk).first()
    if g is None or not is_member(request.user, g):
        return None
    return g


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def categories(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if request.method == "POST":
        if not is_group_admin(request.user, g):
            return Response({"detail": "Only admins can add categories."}, status=403)
        s = CategoryCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cat, created = Category.objects.get_or_create(
            group=g, ledger_type=s.validated_data["ledger_type"], name=s.validated_data["name"].strip(),
            defaults={"color": s.validated_data["color"], "created_by": request.user},
        )
        return Response(CategorySerializer(cat).data, status=201 if created else 200)
    kind = request.query_params.get("ledger")
    if kind and kind not in CATEGORY_KINDS:
        return Response({"detail": "Invalid ledger kind."}, status=400)
    qs = Category.objects.filter(group=g, is_archived=False)
    if kind:
        qs = qs.filter(ledger_type=kind)
    return Response(CategorySerializer(qs, many=True).data)


def _active_member_ids(group):
    return set(str(uid) for uid in GroupMembership.objects.filter(
        group=group, status="active").values_list("user_id", flat=True))


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def expenses(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if request.method == "POST":
        if not is_group_admin(request.user, g):
            return Response({"detail": "Only admins can record expenses."}, status=403)
        return _create_expense(request, g)
    return _list_expenses(request, g)


def _create_expense(request, g):
    s = ExpenseCreateSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    member_ids = _active_member_ids(g)
    cat = Category.objects.filter(pk=d["category"], group=g, ledger_type=_cat_kind(d["ledger_type"])).first()
    if cat is None:
        return Response({"detail": "Invalid category for this ledger."}, status=400)
    if str(d["paid_by"]) not in member_ids:
        return Response({"detail": "Payer must be an active member."}, status=400)

    share_rows = []
    if d["ledger_type"] != "kitchen":
        involved = d["involved"]
        custom = d["shares"]
        ids_used = [str(c["user"]) for c in custom] if d["split_type"] == "custom" else [str(u) for u in involved]
        if any(uid not in member_ids for uid in ids_used):
            return Response({"detail": "All split members must be active members."}, status=400)
        users_by_id = {str(u.id): u for u in User.objects.filter(id__in=ids_used)}
        if d["split_type"] == "custom":
            pairs = splits.build_shares(d["amount"], "custom", None,
                [{"user": users_by_id[str(c["user"])], "amount": c["amount"]} for c in custom])
        else:
            pairs = splits.build_shares(d["amount"], "equal",
                [users_by_id[str(u)] for u in involved], None)
        share_rows = pairs

    period, _ = LedgerPeriod.objects.get_or_create(
        group=g, ledger_type=d["ledger_type"], year=d["date"].year, month=d["date"].month)

    with transaction.atomic():
        locked = LedgerPeriod.objects.select_for_update().get(pk=period.pk)
        if locked.status == LedgerPeriod.FINALIZED:
            raise PermissionDenied("This month is finalized and locked.")
        try:
            exp = Expense.objects.create(
                group=g, ledger_type=d["ledger_type"], category=cat, title=d["title"],
                amount=d["amount"], paid_by_id=d["paid_by"], date=d["date"],
                split_type=("" if d["ledger_type"] == "kitchen" else d["split_type"]),
                created_by=request.user,
            )
            ExpenseShare.objects.bulk_create([
                ExpenseShare(expense=exp, user=u, amount=amt) for (u, amt) in share_rows
            ])
        except IntegrityError:
            return Response({"detail": "Invalid split."}, status=400)
    return Response(ExpenseSerializer(_load(exp.id)).data, status=201)


def _cat_kind(ledger_type):
    return "kitchen_pool" if ledger_type == "kitchen" else ledger_type


def _load(expense_id):
    return Expense.objects.select_related("paid_by", "category").prefetch_related("shares__user").get(id=expense_id)


def _list_expenses(request, g):
    ledger = request.query_params.get("ledger")
    year = request.query_params.get("year")
    month = request.query_params.get("month")
    qs = Expense.objects.filter(group=g).select_related("paid_by", "category").prefetch_related("shares__user")
    if ledger:
        qs = qs.filter(ledger_type=ledger)
    if year:
        qs = qs.filter(date__year=int(year))
    if month:
        qs = qs.filter(date__month=int(month))
    return Response(ExpenseSerializer(qs, many=True).data)


def _expense_or_404(request, pk, need_admin=False):
    exp = Expense.objects.select_related("group", "paid_by", "category").prefetch_related("shares__user").filter(pk=pk).first()
    if exp is None or not is_member(request.user, exp.group):
        return None, Response({"detail": "Not found."}, status=404)
    if need_admin and not is_group_admin(request.user, exp.group):
        return None, Response({"detail": "Only admins can modify expenses."}, status=403)
    return exp, None


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def expense_detail(request, pk):
    need_admin = request.method in ("PATCH", "DELETE")
    exp, err = _expense_or_404(request, pk, need_admin=need_admin)
    if err:
        return err
    if request.method == "GET":
        return Response(ExpenseSerializer(exp).data)
    if request.method == "DELETE":
        LedgerPeriod.ensure_writable(exp.group, exp.ledger_type, exp.date.year, exp.date.month)
        exp.delete()
        return Response({"detail": "deleted"})
    return _update_expense(request, exp)


def _update_expense(request, exp):
    member_ids = _active_member_ids(exp.group)
    data = request.data
    recompute = exp.ledger_type != "kitchen" and any(k in data for k in ("amount", "split_type", "involved", "shares"))

    new_amount = None
    if "amount" in data:
        try:
            new_amount = Decimal(str(data["amount"]))
        except Exception:
            return Response({"detail": "Invalid amount."}, status=400)
        if new_amount <= 0:
            return Response({"detail": "Amount must be greater than zero."}, status=400)

    if "paid_by" in data and str(data["paid_by"]) not in member_ids:
        return Response({"detail": "Payer must be an active member."}, status=400)

    new_date = exp.date
    if "date" in data:
        parsed = parse_date(str(data["date"]))
        if parsed is None:
            return Response({"detail": "Invalid date."}, status=400)
        new_date = parsed

    amount_for_split = new_amount if new_amount is not None else exp.amount

    pairs = None
    split_type = None
    if recompute:
        split_type = data.get("split_type", exp.split_type) or "equal"
        if split_type == "custom":
            if "shares" not in data:
                return Response({"detail": "Provide updated shares for a custom split."}, status=400)
            ids = [str(c["user"]) for c in data["shares"]]
            if any(uid not in member_ids for uid in ids):
                return Response({"detail": "All split members must be active members."}, status=400)
            users = {str(u.id): u for u in User.objects.filter(id__in=ids)}
            custom = [{"user": users[str(c["user"])], "amount": c["amount"]} for c in data["shares"]]
            try:
                pairs = splits.build_shares(amount_for_split, "custom", None, custom)
            except serializers.ValidationError as e:
                return Response({"detail": _first_detail(e)}, status=400)
        else:
            involved_ids = [str(u) for u in data["involved"]] if "involved" in data else [str(s.user_id) for s in exp.shares.all()]
            if not involved_ids:
                return Response({"detail": "Select at least one member to split between."}, status=400)
            if any(uid not in member_ids for uid in involved_ids):
                return Response({"detail": "All split members must be active members."}, status=400)
            users = {str(u.id): u for u in User.objects.filter(id__in=involved_ids)}
            try:
                pairs = splits.build_shares(amount_for_split, "equal", [users[uid] for uid in involved_ids], None)
            except serializers.ValidationError as e:
                return Response({"detail": _first_detail(e)}, status=400)

    with transaction.atomic():
        old_p, _ = LedgerPeriod.objects.get_or_create(
            group=exp.group, ledger_type=exp.ledger_type, year=exp.date.year, month=exp.date.month)
        old_locked = LedgerPeriod.objects.select_for_update().get(pk=old_p.pk)
        if old_locked.status == LedgerPeriod.FINALIZED:
            raise PermissionDenied("This month is finalized and locked.")
        if (new_date.year, new_date.month) != (exp.date.year, exp.date.month):
            new_p, _ = LedgerPeriod.objects.get_or_create(
                group=exp.group, ledger_type=exp.ledger_type, year=new_date.year, month=new_date.month)
            new_locked = LedgerPeriod.objects.select_for_update().get(pk=new_p.pk)
            if new_locked.status == LedgerPeriod.FINALIZED:
                raise PermissionDenied("The target month is finalized and locked.")
        if new_amount is not None:
            exp.amount = new_amount
        if "title" in data:
            exp.title = data["title"]
        exp.date = new_date
        if "paid_by" in data:
            exp.paid_by_id = data["paid_by"]
        if recompute:
            exp.split_type = split_type
        exp.save()
        if recompute:
            exp.shares.all().delete()
            ExpenseShare.objects.bulk_create([ExpenseShare(expense=exp, user=u, amount=amt) for (u, amt) in pairs])
    return Response(ExpenseSerializer(_load(exp.id)).data)


def _first_detail(exc):
    d = exc.detail
    if isinstance(d, list) and d:
        return str(d[0])
    return str(d)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def periods(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    qs = LedgerPeriod.objects.filter(group=g)
    ledger = request.query_params.get("ledger")
    if ledger:
        qs = qs.filter(ledger_type=ledger)
    return Response([
        {"year": p.year, "month": p.month, "status": p.status, "ledger_type": p.ledger_type}
        for p in qs.order_by("-year", "-month")
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def finalize_period(request, pk, ledger, year, month):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can finalize."}, status=403)
    with transaction.atomic():
        p, _ = LedgerPeriod.objects.select_for_update().get_or_create(
            group=g, ledger_type=ledger, year=year, month=month)
        if p.status != LedgerPeriod.FINALIZED:
            p.status = LedgerPeriod.FINALIZED
            p.finalized_by = request.user
            p.finalized_at = timezone.now()
            p.save(update_fields=["status", "finalized_by", "finalized_at"])
    return Response({"detail": "finalized", "year": p.year, "month": p.month, "status": p.status})
