import uuid
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from .constants import CATEGORY_KINDS, LEDGER_TYPES

CATEGORY_KIND_CHOICES = [(k, k) for k in CATEGORY_KINDS]
LEDGER_TYPE_CHOICES = [(t, t) for t in LEDGER_TYPES]


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey("social.Group", on_delete=models.CASCADE, related_name="categories")
    ledger_type = models.CharField(max_length=20, choices=CATEGORY_KIND_CHOICES)
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=9, blank=True)
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "ledger_type", "name"], name="uniq_category_name")]
        ordering = ("name",)


class LedgerPeriod(models.Model):
    OPEN, FINALIZED = "open", "finalized"
    STATUS = ((OPEN, "open"), (FINALIZED, "finalized"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey("social.Group", on_delete=models.CASCADE, related_name="ledger_periods")
    ledger_type = models.CharField(max_length=20, choices=LEDGER_TYPE_CHOICES)
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=STATUS, default=OPEN)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["group", "ledger_type", "year", "month"], name="uniq_period")]

    @classmethod
    def status_for(cls, group, ledger_type, year, month):
        p = cls.objects.filter(group=group, ledger_type=ledger_type, year=year, month=month).first()
        return p.status if p else cls.OPEN

    @classmethod
    def ensure_writable(cls, group, ledger_type, year, month):
        if cls.status_for(group, ledger_type, year, month) == cls.FINALIZED:
            raise PermissionDenied("This month is finalized and locked.")


class Expense(models.Model):
    EQUAL, CUSTOM = "equal", "custom"
    SPLIT = ((EQUAL, "equal"), (CUSTOM, "custom"))
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey("social.Group", on_delete=models.CASCADE, related_name="expenses")
    ledger_type = models.CharField(max_length=20, choices=LEDGER_TYPE_CHOICES)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="expenses")
    title = models.CharField(max_length=160, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    date = models.DateField()
    split_type = models.CharField(max_length=10, choices=SPLIT, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-created_at")


class ExpenseShare(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="shares")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["expense", "user"], name="uniq_expense_share")]
