from decimal import Decimal
from rest_framework import serializers
from apps.accounts.serializers import UserSerializer
from .models import MealEvent, MealAttendance, ExtraAmount, AttendanceDispute


class MealEventCreateSerializer(serializers.Serializer):
    category = serializers.UUIDField()
    date = serializers.DateField()
    note = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")


class AttendanceEntrySerializer(serializers.Serializer):
    user = serializers.UUIDField()
    multiplier = serializers.IntegerField(min_value=1, default=1)
    guest_label = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class RosterSerializer(serializers.Serializer):
    entries = AttendanceEntrySerializer(many=True)


class AttendanceSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    user = UserSerializer(read_only=True)
    multiplier = serializers.IntegerField(read_only=True)
    guest_label = serializers.CharField(read_only=True)


class ExtraSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    paid_by = UserSerializer(read_only=True)


class ExtraCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    paid_by = serializers.UUIDField()


class MealEventSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    category = serializers.UUIDField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    date = serializers.DateField(read_only=True)
    note = serializers.CharField(read_only=True)
    attendance = AttendanceSerializer(many=True, read_only=True)


class MealEventDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    category = serializers.UUIDField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    date = serializers.DateField(read_only=True)
    note = serializers.CharField(read_only=True)
    attendance = AttendanceSerializer(many=True, read_only=True)
    extras = ExtraSerializer(many=True, read_only=True)


class AttendanceHistorySerializer(serializers.ModelSerializer):
    attendance_id = serializers.UUIDField(source="id", read_only=True)
    event_id = serializers.UUIDField(source="meal_event_id", read_only=True)
    date = serializers.DateField(source="meal_event.date", read_only=True)
    category_name = serializers.CharField(source="meal_event.category.name", read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = MealAttendance
        fields = ["attendance_id", "event_id", "date", "category_name", "multiplier", "guest_label", "user"]


class PerUserUnitsSerializer(serializers.Serializer):
    user = UserSerializer(read_only=True)
    units = serializers.IntegerField()


class PoolSummarySerializer(serializers.Serializer):
    category = serializers.UUIDField()
    category_name = serializers.CharField()
    total_units = serializers.IntegerField()
    extras_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    per_user = PerUserUnitsSerializer(many=True)


class DisputeSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    raised_by = UserSerializer(read_only=True)
    meal_event_id = serializers.UUIDField(read_only=True)
    event_date = serializers.DateField(source="meal_event.date", read_only=True)
    pool_name = serializers.CharField(source="meal_event.category.name", read_only=True)

    class Meta:
        model = AttendanceDispute
        fields = [
            "id", "meal_event_id", "user", "raised_by", "reason", "status",
            "event_date", "pool_name", "created_at",
        ]


class DisputeCreateSerializer(serializers.Serializer):
    reason = serializers.CharField()


class DisputeResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["resolve", "reject"])
