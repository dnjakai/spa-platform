from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.context import tenant_context
from apps.tenants.models import Domain, Tenant
from apps.tenants.services import provision_tenant

DEMO = [
    # name, slug, type, plan, city, colour, status, custom domain
    ("Amani Day Spa", "amani", "spa", "business", "Nairobi", "#2f6f62", "active", "book.amanispa.test"),
    ("Fade Factory Barbers", "fade", "barbershop", "growth", "Mombasa", "#b4532a", "active", None),
    ("Lulu Nail Studio", "lulu", "nail_bar", "starter", "Kisumu", "#be185d", "trial", None),
]
DEMO_PASSWORD = "demo-pass-2026"


class Command(BaseCommand):
    help = "Create a platform superuser and three demo businesses with sample bookings (development only)."

    def handle(self, *args, **opts):
        User = get_user_model()
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@platform.test", DEMO_PASSWORD)
            self.stdout.write(self.style.SUCCESS(f"Platform admin: admin / {DEMO_PASSWORD}"))

        for name, slug, kind, plan, city, colour, status, custom in DEMO:
            if Tenant.objects.filter(slug=slug).exists():
                self.stdout.write(f"{name} already exists, skipping")
                continue
            result = provision_tenant(
                name=name, slug=slug, owner_email=f"owner@{slug}.test", plan_code=plan,
                business_type=kind, city=city, brand_color=colour, status=status,
                owner_first_name="Demo", owner_last_name="Owner", password=DEMO_PASSWORD,
            )
            if custom:
                Domain.objects.create(tenant=result.tenant, domain=custom, is_primary=False, verified_at=timezone.now())
            self._sample_bookings(result.tenant)
            self.stdout.write(self.style.SUCCESS(
                f"{name}: http://{slug}.localhost:8000/  (owner@{slug}.test / {DEMO_PASSWORD})"
            ))

    def _sample_bookings(self, tenant):
        from apps.spa.models import Booking, Branch, Customer, Service

        names = [("Mary Njeri", "0722118204"), ("James Otieno", "0733610977"), ("Aisha Hassan", "0711402885"),
                 ("Peter Mwangi", "0745908312")]
        with tenant_context(tenant):
            branch = Branch.objects.first()
            services = list(Service.objects.all()[:4])
            day = timezone.localdate()
            for i, (name, phone) in enumerate(names):
                customer, _ = Customer.objects.get_or_create(phone=phone, defaults={"name": name})
                service = services[i % len(services)]
                start = timezone.make_aware(datetime.combine(day, datetime.min.time()) + timedelta(hours=10 + i * 2))
                Booking.objects.create(
                    customer=customer, service=service, branch=branch, start=start,
                    status=[Booking.Status.COMPLETED, Booking.Status.CONFIRMED, Booking.Status.CONFIRMED,
                            Booking.Status.PENDING_PAYMENT][i],
                    source=Booking.Source.ONLINE if i % 2 else Booking.Source.WALK_IN,
                )
