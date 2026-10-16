from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .context import get_current_tenant

RESERVED_SLUGS = {"www", "admin", "api", "app", "mail", "static", "media", "dashboard", "platform", "support"}

slug_validator = RegexValidator(
    r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$",
    "Use 3–40 lowercase letters, digits or hyphens, starting and ending with a letter or digit.",
)
hex_color_validator = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a hex colour such as #2f6f62.")
domain_validator = RegexValidator(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    "Enter a domain such as book.amanispa.co.ke (no http:// and no path).",
)


def validate_slug_not_reserved(value):
    if value in RESERVED_SLUGS:
        raise ValidationError(f'"{value}" is reserved. Choose another web address.')


# --------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------
class Plan(models.Model):
    """A subscription plan. Limits are enforced in code, not just shown in UI."""

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=50)
    monthly_price_kes = models.PositiveIntegerField()
    setup_fee_kes = models.PositiveIntegerField(default=0)
    max_branches = models.PositiveIntegerField(help_text="0 means unlimited")
    max_staff = models.PositiveIntegerField(help_text="0 means unlimited")
    allows_custom_domain = models.BooleanField(default=False)
    allows_white_label = models.BooleanField(default=False, help_text="Hides 'Powered by' and platform branding")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "monthly_price_kes"]

    def __str__(self):
        return f"{self.name} (KES {self.monthly_price_kes:,}/mo)"

    def limit_reached(self, limit_field, current_count):
        limit = getattr(self, limit_field)
        return bool(limit) and current_count >= limit


# --------------------------------------------------------------------------
# Tenants
# --------------------------------------------------------------------------
class Tenant(models.Model):
    """A business that rents the platform: one spa, salon or barbershop brand."""

    class BusinessType(models.TextChoices):
        SPA = "spa", "Spa"
        BARBERSHOP = "barbershop", "Barbershop"
        NAIL_BAR = "nail_bar", "Nail bar"
        HAIR_SALON = "hair_salon", "Hair salon"
        WELLNESS = "wellness", "Wellness or physio"

    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Payment overdue"
        SUSPENDED = "suspended", "Suspended"
        CHURNED = "churned", "Cancelled"

    class FontStyle(models.TextChoices):
        MODERN = "modern", "Modern sans"
        CLASSIC = "classic", "Classic serif"

    class MpesaType(models.TextChoices):
        PAYBILL = "paybill", "Paybill"
        TILL = "till", "Buy Goods till"

    name = models.CharField(max_length=120)
    slug = models.CharField(
        max_length=40,
        unique=True,
        validators=[slug_validator, validate_slug_not_reserved],
        help_text="Used for the free web address: <slug>.platform domain",
    )
    business_type = models.CharField(max_length=20, choices=BusinessType.choices, default=BusinessType.SPA)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="tenants")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL, db_index=True)
    trial_ends_on = models.DateField(null=True, blank=True)

    # Branding
    brand_color = models.CharField(max_length=7, default="#2f6f62", validators=[hex_color_validator])
    font_style = models.CharField(max_length=10, choices=FontStyle.choices, default=FontStyle.MODERN)
    tagline = models.CharField(max_length=160, blank=True)
    logo = models.FileField(upload_to="tenant-logos/", blank=True)

    # Contact and location
    city = models.CharField(max_length=80, default="Nairobi")
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)

    # Kenya compliance and payments. Each business is paid into its own account.
    kra_pin = models.CharField(
        "KRA PIN",
        max_length=11,
        blank=True,
        validators=[RegexValidator(r"^[A-Z]\d{9}[A-Z]$", "KRA PINs look like P051234567X.")],
    )
    mpesa_type = models.CharField(max_length=10, choices=MpesaType.choices, blank=True)
    mpesa_shortcode = models.CharField("M-Pesa paybill or till number", max_length=10, blank=True)
    # Daraja consumer key/secret/passkey belong in a secrets store keyed by tenant
    # id, never in this table. See README "Next steps".

    sold_by = models.CharField("Reseller", max_length=120, blank=True, help_text="Leave blank for direct sales")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.slug = (self.slug or "").lower()
        if not self.pk and self.status == self.Status.TRIAL and not self.trial_ends_on:
            self.trial_ends_on = timezone.localdate() + timedelta(days=settings.TRIAL_DAYS)
        super().save(*args, **kwargs)

    # Helpers -----------------------------------------------------------------
    @property
    def is_live(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE, self.Status.PAST_DUE}

    @property
    def subdomain(self):
        return f"{self.slug}.{settings.PLATFORM_DOMAIN}"

    @property
    def primary_host(self):
        """The address customers should see, respecting the plan's limits."""
        domain = (
            self.domains.filter(is_primary=True).first()
            if self.plan.allows_custom_domain
            else None
        )
        return domain.domain if domain else self.subdomain

    @property
    def show_powered_by(self):
        return not self.plan.allows_white_label

    @property
    def monthly_fee_kes(self):
        return self.plan.monthly_price_kes


class Domain(models.Model):
    """A web address that serves one tenant. Every tenant has its subdomain."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains")
    domain = models.CharField(max_length=253, unique=True, validators=[domain_validator])
    is_primary = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False, help_text="The business's own domain, not our subdomain")
    verified_at = models.DateTimeField(null=True, blank=True, help_text="Set once DNS points at the platform")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "domain"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(is_primary=True), name="one_primary_domain_per_tenant"
            )
        ]

    def __str__(self):
        return self.domain

    def clean(self):
        self.domain = (self.domain or "").strip().lower().rstrip(".")
        platform_suffix = "." + settings.PLATFORM_DOMAIN
        self.is_custom = not self.domain.endswith(platform_suffix)
        if self.is_custom and self.tenant_id and not self.tenant.plan.allows_custom_domain:
            raise ValidationError(
                {"domain": f"The {self.tenant.plan.name} plan does not include custom domains. Upgrade the plan first."}
            )
        if not self.is_custom:
            label = self.domain[: -len(platform_suffix)]
            if "." in label:
                raise ValidationError({"domain": "Use a single-level subdomain of the platform domain."})

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower().rstrip(".")
        self.is_custom = not self.domain.endswith("." + settings.PLATFORM_DOMAIN)
        if self.is_primary:
            Domain.objects.filter(tenant=self.tenant, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class TenantMembership(models.Model):
    """Gives a user a role inside one business."""

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Branch manager"
        RECEPTIONIST = "receptionist", "Receptionist"
        THERAPIST = "therapist", "Therapist / stylist"
        FINANCE = "finance", "Finance"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="one_membership_per_user_per_tenant")]

    def __str__(self):
        return f"{self.user} · {self.get_role_display()} at {self.tenant}"


# --------------------------------------------------------------------------
# Base class for every per-business table
# --------------------------------------------------------------------------
class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """
    Filters to the current tenant automatically when one is active.

    On a business's domain every query through `.objects` is limited to that
    business, so a forgotten filter cannot leak another business's data. On the
    platform domain (owner admin) no tenant is active and all rows are visible.
    Use `.all_objects` when code must deliberately cross tenants.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        return qs.filter(tenant=tenant) if tenant is not None else qs


class TenantScopedModel(models.Model):
    # Editable so the platform admin can pick a business; tenant-facing forms
    # never include it (the middleware supplies it).
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="+")

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        current = get_current_tenant()
        if not self.tenant_id:
            if current is None:
                raise ValidationError(f"{type(self).__name__} needs a tenant: none is active and none was set.")
            self.tenant = current
        elif current is not None and self.tenant_id != current.pk:
            raise ValidationError(f"Refusing to save {type(self).__name__} for another business.")
        super().save(*args, **kwargs)
