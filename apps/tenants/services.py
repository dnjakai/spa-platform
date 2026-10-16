"""Creating ("provisioning") a new business on the platform."""
import secrets
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from .catalogue import DEFAULT_TAGLINES, STARTER_SERVICES
from .context import tenant_context
from .models import Domain, Plan, Tenant, TenantMembership


@dataclass
class ProvisionResult:
    tenant: Tenant
    owner: object
    temporary_password: str | None  # None when the owner already had an account


def generate_password():
    return secrets.token_urlsafe(9)


@transaction.atomic
def bootstrap_tenant(tenant, *, owner_email, owner_first_name="", owner_last_name="", owner_phone="", password=None):
    """
    Everything a saved Tenant needs to be usable on day one:
    its free subdomain, an owner login, a first branch and a starter service menu.
    Safe to call once per tenant; called by `provision_tenant` and the admin.
    """
    from apps.spa.models import Branch, Service  # avoid an import cycle

    if not tenant.tagline:
        tenant.tagline = DEFAULT_TAGLINES.get(tenant.business_type, "")
        tenant.save(update_fields=["tagline"])

    Domain.objects.get_or_create(
        domain=tenant.subdomain, defaults={"tenant": tenant, "is_primary": not tenant.domains.exists()}
    )

    User = get_user_model()
    owner = User.objects.filter(email__iexact=owner_email).first()
    temporary_password = None
    if owner is None:
        temporary_password = password or generate_password()
        owner = User.objects.create_user(
            username=owner_email.lower(),
            email=owner_email.lower(),
            password=temporary_password,
            first_name=owner_first_name,
            last_name=owner_last_name,
            phone=owner_phone,
        )
    TenantMembership.objects.get_or_create(
        tenant=tenant, user=owner, defaults={"role": TenantMembership.Role.OWNER}
    )

    with tenant_context(tenant):
        if not Branch.objects.exists():
            Branch.objects.create(name="Main branch", city=tenant.city, phone=tenant.contact_phone)
        if not Service.objects.exists():
            Service.objects.bulk_create(
                [
                    Service(tenant=tenant, name=name, duration_minutes=minutes, price_kes=price, sort_order=i)
                    for i, (name, minutes, price) in enumerate(STARTER_SERVICES.get(tenant.business_type, []))
                ]
            )

    return ProvisionResult(tenant=tenant, owner=owner, temporary_password=temporary_password)


@transaction.atomic
def provision_tenant(
    *,
    name,
    slug,
    owner_email,
    plan_code="starter",
    business_type=Tenant.BusinessType.SPA,
    city="Nairobi",
    brand_color="#2f6f62",
    owner_first_name="",
    owner_last_name="",
    owner_phone="",
    password=None,
    status=Tenant.Status.TRIAL,
):
    """Create a business and everything it needs. Raises ValidationError on bad input."""
    tenant = Tenant(
        name=name,
        slug=slug.lower(),
        business_type=business_type,
        plan=Plan.objects.get(code=plan_code),
        city=city,
        brand_color=brand_color,
        status=status,
        contact_email=owner_email,
        contact_phone=owner_phone,
    )
    tenant.full_clean()
    tenant.save()
    return bootstrap_tenant(
        tenant,
        owner_email=owner_email,
        owner_first_name=owner_first_name,
        owner_last_name=owner_last_name,
        owner_phone=owner_phone,
        password=password,
    )


def tenant_url(tenant, path="/", request=None):
    """Absolute URL on the tenant's primary address (keeps the dev port)."""
    scheme = "https" if not settings.DEBUG else "http"
    port = ""
    if request is not None:
        scheme = request.scheme
        p = request.get_port()
        port = "" if p in {"80", "443"} else f":{p}"
    return f"{scheme}://{tenant.primary_host}{port}{path}"
