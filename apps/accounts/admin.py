from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "phone", "is_staff", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    fieldsets = BaseUserAdmin.fieldsets + (("Contact", {"fields": ("phone",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("Contact", {"fields": ("email", "phone")}),)
