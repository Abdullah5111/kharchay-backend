from django.contrib import admin
from .models import Category, Expense, ExpenseShare, LedgerPeriod


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "ledger_type", "group", "is_archived", "created_at")
    list_filter = ("ledger_type", "is_archived")
    search_fields = ("name",)


@admin.register(LedgerPeriod)
class LedgerPeriodAdmin(admin.ModelAdmin):
    list_display = ("group", "ledger_type", "year", "month", "status", "finalized_at")
    list_filter = ("ledger_type", "status")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("title", "ledger_type", "group", "amount", "paid_by", "date", "created_at")
    list_filter = ("ledger_type",)
    search_fields = ("title",)


@admin.register(ExpenseShare)
class ExpenseShareAdmin(admin.ModelAdmin):
    list_display = ("expense", "user", "amount")
