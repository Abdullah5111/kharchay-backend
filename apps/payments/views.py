from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone

from apps.social.models import Group, GroupMembership
from apps.social.permissions import is_member, is_group_admin
from apps.notifications.services import notify
from apps.settlement.models import Settlement

from .models import Payment
from .serializers import PaymentSerializer, PaymentSubmitSerializer
from . import storage


def _group_or_404(request, pk):
    g = Group.objects.filter(pk=pk).first()
    return g if (g and is_member(request.user, g)) else None


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def payments(request, pk):
    g = _group_or_404(request, pk)
    if g is None:
        return Response({"detail": "Not found."}, status=404)

    if request.method == "POST":
        s = PaymentSubmitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data

        proof_key = ""
        proof_file = request.FILES.get("proof")
        if proof_file:
            try:
                storage.validate_image(proof_file)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            proof_key = storage.save_proof(g.id, proof_file)

        settlement = Settlement.objects.filter(
            group=g, year=d["year"], month=d["month"]
        ).first()

        payment = Payment.objects.create(
            group=g,
            user=request.user,
            settlement=settlement,
            year=d["year"],
            month=d["month"],
            amount=d["amount"],
            method=d.get("method", ""),
            proof_image=proof_key,
        )

        # Notify group admins (exclude payer)
        admin_memberships = GroupMembership.objects.filter(
            group=g,
            status="active",
            role__in=["owner", "admin"],
        ).exclude(user=request.user).select_related("user")
        admin_users = [m.user for m in admin_memberships]
        if admin_users:
            notify(
                admin_users,
                "payment_submitted",
                "Payment Submitted",
                f"{request.user.name} submitted a payment of {payment.amount} for {payment.month}/{payment.year}.",
                {"payment_id": str(payment.id), "group_id": str(g.id)},
            )

        return Response(
            PaymentSerializer(payment, context={"request": request}).data,
            status=201,
        )

    # GET — admin only
    if not is_group_admin(request.user, g):
        return Response({"detail": "Only admins can view group payments."}, status=403)

    qs = Payment.objects.filter(group=g).select_related("user", "reviewed_by")

    status_filter = request.query_params.get("status")
    year_filter = request.query_params.get("year")
    month_filter = request.query_params.get("month")

    if year_filter is not None:
        try:
            year_filter = int(year_filter)
        except (ValueError, TypeError):
            return Response({"detail": "year and month must be integers."}, status=400)
    if month_filter is not None:
        try:
            month_filter = int(month_filter)
        except (ValueError, TypeError):
            return Response({"detail": "year and month must be integers."}, status=400)

    if status_filter:
        qs = qs.filter(status=status_filter)
    if year_filter is not None:
        qs = qs.filter(year=year_filter)
    if month_filter is not None:
        qs = qs.filter(month=month_filter)

    return Response(PaymentSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_payments(request):
    group_id = request.query_params.get("group")
    if not group_id:
        return Response({"detail": "group parameter is required."}, status=400)

    g = Group.objects.filter(pk=group_id).first()
    if g is None or not is_member(request.user, g):
        return Response({"detail": "Not found."}, status=404)

    qs = Payment.objects.filter(group=g, user=request.user).select_related("user", "reviewed_by")

    year_filter = request.query_params.get("year")
    month_filter = request.query_params.get("month")

    if year_filter is not None:
        try:
            year_filter = int(year_filter)
        except (ValueError, TypeError):
            return Response({"detail": "year and month must be integers."}, status=400)
    if month_filter is not None:
        try:
            month_filter = int(month_filter)
        except (ValueError, TypeError):
            return Response({"detail": "year and month must be integers."}, status=400)

    if year_filter is not None:
        qs = qs.filter(year=year_filter)
    if month_filter is not None:
        qs = qs.filter(month=month_filter)

    return Response(PaymentSerializer(qs, many=True, context={"request": request}).data)


def _payment_or_404(request, payment_id):
    """
    Load Payment by id. Return (payment, error_response) where one will be None.
    - 404 if payment doesn't exist OR the requesting user is not a member of the payment's group
    - 403 if user is a member but not an admin
    """
    payment = Payment.objects.filter(pk=payment_id).select_related("group", "user").first()
    if payment is None:
        return None, Response({"detail": "Not found."}, status=404)
    if not is_member(request.user, payment.group):
        return None, Response({"detail": "Not found."}, status=404)
    if not is_group_admin(request.user, payment.group):
        return None, Response({"detail": "You do not have permission to perform this action."}, status=403)
    return payment, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_payment(request, payment_id):
    payment, err = _payment_or_404(request, payment_id)
    if err is not None:
        return err

    if payment.status != Payment.SUBMITTED:
        return Response({"detail": "Only a submitted payment can be reviewed."}, status=400)

    with transaction.atomic():
        payment.status = Payment.APPROVED
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.review_note = request.data.get("review_note", "")
        payment.save()

    notify(
        [payment.user],
        "payment_approved",
        "Payment Approved",
        f"Your payment of {payment.amount} for {payment.month}/{payment.year} has been approved.",
        {"payment_id": str(payment.id), "group_id": str(payment.group.id)},
    )

    return Response(PaymentSerializer(payment, context={"request": request}).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_payment(request, payment_id):
    payment, err = _payment_or_404(request, payment_id)
    if err is not None:
        return err

    if payment.status != Payment.SUBMITTED:
        return Response({"detail": "Only a submitted payment can be reviewed."}, status=400)

    with transaction.atomic():
        payment.status = Payment.REJECTED
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.review_note = request.data.get("review_note", "")
        payment.save()

    notify(
        [payment.user],
        "payment_rejected",
        "Payment Rejected",
        f"Your payment of {payment.amount} for {payment.month}/{payment.year} has been rejected.",
        {"payment_id": str(payment.id), "group_id": str(payment.group.id)},
    )

    return Response(PaymentSerializer(payment, context={"request": request}).data)
