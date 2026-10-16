"""Platform-admin views of per-business data, filterable by business."""
from django.contrib import admin

from .models import Booking, Branch, Customer, Service, StaffMember


class TenantFilteredAdmin(admin.ModelAdmin):
    list_filter = ("tenant",)
    list_select_related = ("tenant",)


@admin.register(Branch)
class BranchAdmin(TenantFilteredAdmin):
    list_display = ("name", "tenant", "city", "opens_at", "closes_at", "is_active")
    search_fields = ("name", "tenant__name")


@admin.register(Service)
class ServiceAdmin(TenantFilteredAdmin):
    list_display = ("name", "tenant", "duration_minutes", "price_kes", "deposit_percent", "is_active")
    search_fields = ("name", "tenant__name")


@admin.register(StaffMember)
class StaffMemberAdmin(TenantFilteredAdmin):
    list_display = ("name", "tenant", "branch", "commission_percent", "is_active")
    search_fields = ("name", "tenant__name")
    raw_id_fields = ("user",)


@admin.register(Customer)
class CustomerAdmin(TenantFilteredAdmin):
    list_display = ("name", "tenant", "phone", "email", "created_at")
    search_fields = ("name", "phone", "email")
    # Treatment notes are sensitive personal data; platform staff don't need them.
    exclude = ("notes",)


@admin.register(Booking)
class BookingAdmin(TenantFilteredAdmin):
    list_display = ("ref", "tenant", "customer", "service", "branch", "start", "status", "price_kes", "deposit_kes")
    list_filter = ("tenant", "status", "source")
    search_fields = ("ref", "customer__name", "customer__phone")
    date_hierarchy = "start"
    raw_id_fields = ("customer",)
