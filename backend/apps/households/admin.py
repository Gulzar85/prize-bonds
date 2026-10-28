from django.contrib import admin

from apps.households.models import Household, Membership


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ["name", "created_by", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "household", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["user__email", "household__name"]
    readonly_fields = ["created_at", "updated_at"]
