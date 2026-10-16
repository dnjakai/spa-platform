"""
The platform owner's console (Django admin on the platform domain).

Adding a business here creates the tenant AND bootstraps it: free subdomain,
owner login, first branch and a starter service menu.
"""
from django import forms
from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import Domain, Plan, Tenant, TenantMembership
from .services import bootstrap_tenant, tenant_url


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "name", "monthly_price_kes", "setup_fee_kes", "max_branches", "max_staff",
        "allows_custom_domain", "allows_white_label", "tenant_count",
    )
    ordering = ("sort_order",)

    @admin.display(description="Businesses")
    def tenant_count(self, obj):
        return obj.tenants.count()


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0
    fields = ("domain", "is_primary", "is_custom", "verified_at")
    readonly_fields = ("is_custom",)


class MembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    fields = ("user", "role", "is_active")
    raw_id_fields = ("user",)


class TenantAddForm(forms.ModelForm):
    owner_email = forms.EmailField(help_text="The owner's login. An existing account is reused.")
    owner_first_name = forms.CharField(required=False)
    owner_last_name = forms.CharField(required=False)
    owner_phone = forms.CharField(required=False, help_text="e.g. 0712 345 678")

    class Meta:
        model = Tenant
        fields = (
            "name", "slug", "business_type", "plan", "status", "city",
            "brand_color", "font_style", "sold_by",
        )
        widgets = {"brand_color": forms.TextInput(attrs={"type": "color"})}


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "business_type", "plan", "status_badge", "web_address", "sold_by", "created_at")
    list_filter = ("status", "plan", "business_type", "sold_by")
    search_fields = ("name", "slug", "domains__domain", "contact_email", "contact_phone")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at", "links")
    actions = ("mark_active", "mark_suspended")
    fieldsets = (
        (None, {"fields": ("name", "slug", "business_type", "plan", "status", "trial_ends_on", "sold_by", "links")}),
        ("Branding", {"fields": ("brand_color", "font_style", "tagline", "logo")}),
        ("Contact", {"fields": ("city", "contact_phone", "contact_email")}),
        ("Payments and tax", {"fields": ("mpesa_type", "mpesa_shortcode", "kra_pin")}),
        ("Record", {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        ("Business", {"fields": ("name", "slug", "business_type", "plan", "status", "city", "sold_by")}),
        ("Branding", {"fields": ("brand_color", "font_style")}),
        ("Owner login", {"fields": ("owner_email", "owner_first_name", "owner_last_name", "owner_phone")}),
    )

    # Use the richer form and layout only when adding.
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = TenantAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else super().get_fieldsets(request, obj)

    def get_inlines(self, request, obj):
        return [] if obj is None else [DomainInline, MembershipInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change:
            return
        data = form.cleaned_data
        result = bootstrap_tenant(
            obj,
            owner_email=data["owner_email"],
            owner_first_name=data.get("owner_first_name", ""),
            owner_last_name=data.get("owner_last_name", ""),
            owner_phone=data.get("owner_phone", ""),
        )
        login_url = tenant_url(obj, "/accounts/login/", request)
        if result.temporary_password:
            messages.success(
                request,
                format_html(
                    "{} is ready at <a href='{}'>{}</a>. Owner login: <b>{}</b> / temporary password "
                    "<code>{}</code>. Share it securely; it is not shown again.",
                    obj.name, login_url, login_url, result.owner.email, result.temporary_password,
                ),
            )
        else:
            messages.success(
                request,
                format_html(
                    "{} is ready at <a href='{}'>{}</a>. {} already had an account and was added as owner.",
                    obj.name, login_url, login_url, result.owner.email,
                ),
            )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colours = {"active": "#23794a", "trial": "#2b54c4", "past_due": "#a35b00", "suspended": "#b3352d", "churned": "#666"}
        return format_html(
            "<b style='color:{}'>{}</b>", colours.get(obj.status, "#333"), obj.get_status_display()
        )

    @admin.display(description="Web address")
    def web_address(self, obj):
        return obj.primary_host

    @admin.display(description="Open")
    def links(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            "<a href='{}' target='_blank'>Booking site</a> · <a href='{}' target='_blank'>Business dashboard</a>",
            tenant_url(obj, "/"), tenant_url(obj, "/dashboard/"),
        )

    @admin.action(description="Mark selected businesses as active (paid)")
    def mark_active(self, request, queryset):
        count = queryset.update(status=Tenant.Status.ACTIVE, updated_at=timezone.now())
        self.message_user(request, f"{count} business(es) marked active.")

    @admin.action(description="Suspend selected businesses (sites go offline)")
    def mark_suspended(self, request, queryset):
        count = queryset.update(status=Tenant.Status.SUSPENDED, updated_at=timezone.now())
        self.message_user(request, f"{count} business(es) suspended.", level=messages.WARNING)


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ("domain", "tenant", "is_primary", "is_custom", "verified_at")
    list_filter = ("is_custom", "is_primary")
    search_fields = ("domain", "tenant__name")
    readonly_fields = ("is_custom",)


@admin.register(TenantMembership)
class TenantMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "tenant__name")
    raw_id_fields = ("user", "tenant")
