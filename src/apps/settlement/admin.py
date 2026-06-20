from django.contrib import admin
from .models import Settlement, SettlementLine, Transfer


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("group", "year", "month", "status", "generated_at")


admin.site.register(SettlementLine)
admin.site.register(Transfer)
