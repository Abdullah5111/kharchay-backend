from decimal import Decimal

from django.core.files.storage import default_storage
from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    proof_url = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "user",
            "year",
            "month",
            "amount",
            "method",
            "status",
            "proof_url",
            "review_note",
            "reviewed_by",
            "reviewed_at",
            "submitted_at",
        ]

    def get_proof_url(self, obj):
        if not obj.proof_image:
            return None
        request = self.context.get("request")
        url = default_storage.url(obj.proof_image)
        return request.build_absolute_uri(url) if request else url


class PaymentSubmitSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.CharField(required=False, allow_blank=True, max_length=60)
    year = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
