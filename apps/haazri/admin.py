from django.contrib import admin
from .models import MealEvent, MealAttendance, ExtraAmount, AttendanceDispute


class MealAttendanceInline(admin.TabularInline):
    model = MealAttendance
    extra = 0
    fields = ("user", "multiplier", "guest_label")


class ExtraAmountInline(admin.TabularInline):
    model = ExtraAmount
    extra = 0
    fields = ("title", "amount", "paid_by", "created_by")
    readonly_fields = ("created_by",)


@admin.register(MealEvent)
class MealEventAdmin(admin.ModelAdmin):
    list_display = ("id", "group", "category", "date", "created_by", "created_at")
    list_filter = ("date", "group")
    search_fields = ("group__name", "category__name")
    inlines = [MealAttendanceInline, ExtraAmountInline]


@admin.register(MealAttendance)
class MealAttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "meal_event", "user", "multiplier", "guest_label", "created_at")
    list_filter = ("meal_event__date",)
    search_fields = ("user__email", "user__name")


@admin.register(ExtraAmount)
class ExtraAmountAdmin(admin.ModelAdmin):
    list_display = ("id", "meal_event", "title", "amount", "paid_by", "created_by", "created_at")
    list_filter = ("meal_event__date",)
    search_fields = ("title", "paid_by__email", "paid_by__name")


@admin.register(AttendanceDispute)
class AttendanceDisputeAdmin(admin.ModelAdmin):
    list_display = ("id", "meal_event", "user", "raised_by", "status", "resolved_by", "created_at", "resolved_at")
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "user__name", "raised_by__email", "reason")
    readonly_fields = ("created_at", "resolved_at")
