import uuid
from django.conf import settings
from django.db import models


class Settlement(models.Model):
    DRAFT, FINALIZED = "draft", "finalized"
    STATUS = ((DRAFT, "draft"), (FINALIZED, "finalized"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey("social.Group", on_delete=models.CASCADE, related_name="settlements")
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=STATUS, default=DRAFT)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "year", "month"], name="uniq_settlement_period")]
        ordering = ("-year", "-month")


class SettlementLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settlement = models.ForeignKey(Settlement, on_delete=models.CASCADE, related_name="lines")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    paid_total = models.DecimalField(max_digits=12, decimal_places=2)
    owed_total = models.DecimalField(max_digits=12, decimal_places=2)
    net = models.DecimalField(max_digits=12, decimal_places=2)  # owed - paid; positive => owes
    breakdown = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["settlement", "user"], name="uniq_settlement_line")]


class Transfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settlement = models.ForeignKey(Settlement, on_delete=models.CASCADE, related_name="transfers")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
