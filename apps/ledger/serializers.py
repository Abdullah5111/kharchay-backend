from decimal import Decimal
from rest_framework import serializers
from apps.accounts.serializers import UserSerializer
from .constants import CATEGORY_KINDS, LEDGER_TYPES
from .models import Category, Expense, ExpenseShare


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "ledger_type", "name", "color", "is_archived"]
        read_only_fields = ["id", "is_archived"]


class CategoryCreateSerializer(serializers.Serializer):
    ledger_type = serializers.ChoiceField(choices=CATEGORY_KINDS)
    name = serializers.CharField(max_length=80)
    color = serializers.CharField(max_length=9, required=False, allow_blank=True, default="")


class ShareInputSerializer(serializers.Serializer):
    user = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class ExpenseCreateSerializer(serializers.Serializer):
    ledger_type = serializers.ChoiceField(choices=LEDGER_TYPES)
    category = serializers.UUIDField()
    title = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    paid_by = serializers.UUIDField()
    date = serializers.DateField()
    split_type = serializers.ChoiceField(choices=["equal", "custom"], required=False, allow_blank=True, default="")
    involved = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    shares = ShareInputSerializer(many=True, required=False, default=list)


class ShareSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)


class ExpenseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    ledger_type = serializers.CharField(read_only=True)
    category = serializers.UUIDField(source="category_id", read_only=True)
    title = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid_by = UserSerializer(read_only=True)
    date = serializers.DateField(read_only=True)
    split_type = serializers.CharField(read_only=True)
    shares = ShareSerializer(many=True, read_only=True)
