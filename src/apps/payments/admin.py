from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("group", "user", "year", "month", "amount", "status", "submitted_at")
    list_filter = ("status",)
