"""Per-business data. Every model here inherits the tenant column and scoping."""
import secrets
from datetime import time, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.tenants.models import TenantScopedModel

kenyan_phone = RegexValidator(
    r"^(?:\+?254|0)(?:7|1)\d{8}$", "Enter a Kenyan mobile number such as 0712345678 or +254712345678."
)


def normalise_phone(value):
    digits = "".join(ch for ch in (value or "") if ch.isdigit() or ch == "+")
    if digits.startswith("+254"):
        return "0" + digits[4:]
    if digits.startswith("254"):
        return "0" + digits[3:]
    return digits


class Branch(TenantScopedModel):
    name = models.CharField(max_length=80)
    city = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    opens_at = models.TimeField(default=time(9, 0))
    closes_at = models.TimeField(default=time(19, 0))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "branches"
        constraints = [models.UniqueConstraint(fields=["tenant", "name"], name="unique_branch_name_per_tenant")]

    def __str__(self):
        return self.name

    def clean(self):
        if self.tenant_id and not self.pk:
            plan = self.tenant.plan
            existing = Branch.all_objects.filter(tenant_id=self.tenant_id).count()
            if plan.limit_reached("max_branches", existing):
                raise ValidationError(
                    f"The {plan.name} plan allows {plan.max_branches} branch(es). Upgrade to add more."
                )
        if self.opens_at and self.closes_at and self.opens_at >= self.closes_at:
            raise ValidationError("Closing time must be after opening time.")


class Service(TenantScopedModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    price_kes = models.PositiveIntegerField()
    deposit_percent = models.PositiveSmallIntegerField(
        default=settings.DEFAULT_DEPOSIT_PERCENT, validators=[MaxValueValidator(100)]
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def deposit_kes(self):
        # Rounded to the nearest KES 50 so M-Pesa prompts look tidy.
        return int(round(self.price_kes * self.deposit_percent / 100 / 50) * 50)


class StaffMember(TenantScopedModel):
    """A therapist or stylist who can be booked. May or may not have a login."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="staff")
    services = models.ManyToManyField(Service, blank=True, related_name="staff")
    commission_percent = models.PositiveSmallIntegerField(default=10, validators=[MaxValueValidator(100)])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.tenant_id and not self.pk:
            plan = self.tenant.plan
            existing = StaffMember.all_objects.filter(tenant_id=self.tenant_id, is_active=True).count()
            if plan.limit_reached("max_staff", existing):
                raise ValidationError(f"The {plan.name} plan allows {plan.max_staff} staff. Upgrade to add more.")


class Customer(TenantScopedModel):
    """A customer of one business. The same person at two businesses is two records."""

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, validators=[kenyan_phone])
    email = models.EmailField(blank=True)
    marketing_consent = models.BooleanField(default=False)
    notes = models.TextField(blank=True, help_text="Allergies and treatment notes. Sensitive: staff only.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["tenant", "phone"], name="unique_customer_phone_per_tenant")]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def save(self, *args, **kwargs):
        self.phone = normalise_phone(self.phone)
        super().save(*args, **kwargs)


class Booking(TenantScopedModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting deposit"
        CONFIRMED = "confirmed", "Confirmed"
        ARRIVED = "arrived", "Arrived"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No-show"

    class Source(models.TextChoices):
        ONLINE = "online", "Online"
        PHONE = "phone", "Phone"
        WALK_IN = "walk_in", "Walk-in"

    ref = models.CharField(max_length=12, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="bookings")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="bookings")
    staff = models.ForeignKey(StaffMember, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField(editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.ONLINE)
    price_kes = models.PositiveIntegerField(editable=False)
    deposit_kes = models.PositiveIntegerField(default=0)
    mpesa_receipt = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return f"{self.ref} · {self.customer.name} · {self.service.name}"

    def clean(self):
        for field in ("customer", "service", "branch", "staff"):
            related = getattr(self, field, None)
            if related is not None and self.tenant_id and related.tenant_id != self.tenant_id:
                raise ValidationError({field: "Belongs to a different business."})

    def save(self, *args, **kwargs):
        if not self.ref:
            prefix = (self.tenant.slug if self.tenant_id else "BK")[:3].upper()
            self.ref = f"{prefix}-{secrets.token_hex(3).upper()}"
        self.price_kes = self.service.price_kes
        self.end = self.start + timedelta(minutes=self.service.duration_minutes)
        if self.deposit_kes == 0 and self.source == self.Source.ONLINE:
            self.deposit_kes = self.service.deposit_kes
        super().save(*args, **kwargs)

    @property
    def balance_kes(self):
        return max(self.price_kes - self.deposit_kes, 0)

    @property
    def is_upcoming(self):
        return self.start >= timezone.now()
