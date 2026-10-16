from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Plan, Tenant
from apps.tenants.services import provision_tenant


class Command(BaseCommand):
    help = "Create a business (tenant) with its subdomain, owner login, first branch and starter services."

    def add_arguments(self, parser):
        parser.add_argument("name", help='Business name, e.g. "Amani Day Spa"')
        parser.add_argument("slug", help="Web address slug, e.g. amani → amani.<platform domain>")
        parser.add_argument("owner_email")
        parser.add_argument("--plan", default="starter", help="starter, growth or business")
        parser.add_argument("--type", default="spa", choices=[c for c, _ in Tenant.BusinessType.choices])
        parser.add_argument("--city", default="Nairobi")
        parser.add_argument("--color", default="#2f6f62")
        parser.add_argument("--owner-name", default="")
        parser.add_argument("--owner-phone", default="")
        parser.add_argument("--password", help="Set the owner password instead of generating one")

    def handle(self, *args, **opts):
        if not Plan.objects.filter(code=opts["plan"]).exists():
            raise CommandError(f"No plan '{opts['plan']}'. Run migrate first; plans are created by a migration.")
        first, _, last = opts["owner_name"].partition(" ")
        try:
            result = provision_tenant(
                name=opts["name"],
                slug=opts["slug"],
                owner_email=opts["owner_email"],
                plan_code=opts["plan"],
                business_type=opts["type"],
                city=opts["city"],
                brand_color=opts["color"],
                owner_first_name=first,
                owner_last_name=last,
                owner_phone=opts["owner_phone"],
                password=opts["password"],
            )
        except ValidationError as exc:
            raise CommandError("; ".join(f"{k}: {' '.join(v)}" for k, v in exc.message_dict.items()))

        t = result.tenant
        self.stdout.write(self.style.SUCCESS(f"Created {t.name} on the {t.plan.name} plan"))
        self.stdout.write(f"  Booking site: http://{t.primary_host}:8000/")
        self.stdout.write(f"  Dashboard:    http://{t.primary_host}:8000/dashboard/")
        self.stdout.write(f"  Owner login:  {result.owner.email}")
        if result.temporary_password:
            self.stdout.write(f"  Password:     {result.temporary_password}")
