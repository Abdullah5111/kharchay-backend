import uuid
from django.conf import settings
from django.db import models


class Payment(models.Model):
    SUBMITTED, APPROVED, REJECTED = "submitted", "approved", "rejected"
    STATUS = ((SUBMITTED, "submitted"), (APPROVED, "approved"), (REJECTED, "rejected"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey("social.Group", on_delete=models.CASCADE, related_name="payments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    settlement = models.ForeignKey(
        "settlement.Settlement", null=True, blank=True, on_delete=models.SET_NULL, related_name="payments"
    )
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=60, blank=True)
    proof_image = models.CharField(max_length=255, blank=True)  # storage key
    status = models.CharField(max_length=10, choices=STATUS, default=SUBMITTED)
    review_note = models.CharField(max_length=300, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-submitted_at",)
