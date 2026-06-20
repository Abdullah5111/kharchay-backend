from rest_framework import serializers
from apps.accounts.serializers import UserSerializer


class LineOutSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    paid_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    owed_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    net = serializers.DecimalField(max_digits=12, decimal_places=2)
    breakdown = serializers.JSONField()


class TransferOutSerializer(serializers.Serializer):
    from_user = UserSerializer(read_only=True)
    to_user = UserSerializer(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class StandingSerializer(serializers.Serializer):
    """Serializer for the /me/standing/ endpoint.

    paid_total: total the user has paid out
    owed_total: total the user owes (their share of all expenses)
    net: owed_total - paid_total (positive = user owes; negative = user is owed)
    breakdown: per-category detail dict with keys non_kitchen, kitchen, extras, paid
    transfers: only the transfers where this user is from_user or to_user
    settlement_status: "none" if no persisted Settlement for the period, else "draft" or "finalized"
    """
    paid_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    owed_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    net = serializers.DecimalField(max_digits=12, decimal_places=2)
    breakdown = serializers.JSONField()
    transfers = TransferOutSerializer(many=True)
    settlement_status = serializers.CharField()


class ActivityItemSerializer(serializers.Serializer):
    """Serializer for items in the /me/activity/ feed.

    kind: "expense" or "meal"
    date: ISO date string (YYYY-MM-DD)
    title: expense title or category.name for meals
    ledger_type: expense ledger type (present for kind="expense", absent for kind="meal")
    pool_name: kitchen pool category name (present for kind="meal", absent for kind="expense")
    amount: the user's monetary stake — for expenses this is their ExpenseShare amount (or "0.00"
            if they appear only as payer with no share); for meals this is their proportional share
            of the event's total ExtraAmount(s), apportioned by attendance multiplier. If the event
            has no ExtraAmount records, amount = "0.00". Decision: we report the extras share, NOT
            the kitchen-pool meal cost, because the meal cost is already surfaced in the standing
            breakdown and the extras share is what the user owes *specifically for that event*.
    role: "payer" if user paid the expense, else "participant"
    """
    kind = serializers.CharField()
    date = serializers.CharField()
    title = serializers.CharField()
    ledger_type = serializers.CharField(required=False, allow_null=True)
    pool_name = serializers.CharField(required=False, allow_null=True)
    amount = serializers.CharField()
    role = serializers.CharField()
