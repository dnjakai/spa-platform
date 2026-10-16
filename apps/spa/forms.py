from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from apps.tenants.models import Domain, Tenant, domain_validator

from .models import Booking, Branch, Customer, kenyan_phone, normalise_phone


class BookingForm(forms.Form):
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), empty_label=None)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time", "step": 1800}))
    name = forms.CharField(max_length=120, label="Your name")
    phone = forms.CharField(max_length=20, label="M-Pesa phone number", help_text="e.g. 0712 345 678")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}), label="Anything we should know?")
    consent = forms.BooleanField(
        label="I agree that this business may store my details to manage my booking.", required=True
    )

    def __init__(self, *args, service, **kwargs):
        super().__init__(*args, **kwargs)
        self.service = service
        # Branch.objects is already limited to the current business by the middleware.
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True)
        self.fields["date"].initial = timezone.localdate() + timedelta(days=1)

    def clean_phone(self):
        # Accept spaces and +254 by normalising first, then validate.
        phone = normalise_phone(self.cleaned_data["phone"])
        kenyan_phone(phone)
        return phone

    def clean(self):
        data = super().clean()
        branch, day, at = data.get("branch"), data.get("date"), data.get("time")
        if not (branch and day and at):
            return data
        start = timezone.make_aware(datetime.combine(day, at))
        end_time = (datetime.combine(day, at) + timedelta(minutes=self.service.duration_minutes)).time()
        if start <= timezone.now():
            raise forms.ValidationError("Choose a time in the future.")
        if at < branch.opens_at or end_time > branch.closes_at:
            raise forms.ValidationError(
                f"{branch.name} is open {branch.opens_at:%H:%M}–{branch.closes_at:%H:%M}. "
                "Choose a time that ends before closing."
            )
        data["start"] = start
        return data

    def save(self):
        data = self.cleaned_data
        customer, created = Customer.objects.get_or_create(phone=data["phone"], defaults={"name": data["name"]})
        if not created and customer.name != data["name"]:
            customer.name = data["name"]
            customer.save(update_fields=["name"])
        return Booking.objects.create(
            customer=customer, service=self.service, branch=data["branch"], start=data["start"],
            notes=data.get("notes", ""), source=Booking.Source.ONLINE,
        )


class BrandingForm(forms.ModelForm):
    custom_domain = forms.CharField(
        required=False, validators=[domain_validator],
        help_text="Your own address, e.g. book.yourspa.co.ke. Point its DNS at the platform first.",
    )

    class Meta:
        model = Tenant
        fields = ("name", "brand_color", "font_style", "tagline", "contact_phone", "contact_email")
        widgets = {"brand_color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        custom = self.instance.domains.filter(is_custom=True).first()
        self.fields["custom_domain"].initial = custom.domain if custom else ""
        if not self.instance.plan.allows_custom_domain:
            self.fields["custom_domain"].disabled = True
            self.fields["custom_domain"].help_text = (
                f"Custom domains come with the Growth plan. You're on {self.instance.plan.name}."
            )

    def clean_custom_domain(self):
        value = (self.cleaned_data.get("custom_domain") or "").strip().lower().rstrip(".")
        if not value:
            return ""
        if value.endswith("." + settings.PLATFORM_DOMAIN):
            raise forms.ValidationError("That is a platform address. Enter your own domain.")
        if Domain.objects.filter(domain=value).exclude(tenant=self.instance).exists():
            raise forms.ValidationError("That domain is already used by another business.")
        return value

    def save(self, commit=True):
        tenant = super().save(commit)
        value = self.cleaned_data.get("custom_domain")
        if tenant.plan.allows_custom_domain:
            existing = tenant.domains.filter(is_custom=True).first()
            if value and (existing is None or existing.domain != value):
                if existing:
                    existing.delete()
                # Not primary until verified, so the booking link keeps working meanwhile.
                Domain.objects.create(tenant=tenant, domain=value, is_primary=False)
            elif not value and existing:
                existing.delete()
                if not tenant.domains.filter(is_primary=True).exists():
                    tenant.domains.filter(domain=tenant.subdomain).update(is_primary=True)
        return tenant
