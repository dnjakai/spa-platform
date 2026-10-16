"""Creates the three subscription plans from the proposal. Edit prices in the admin later."""
from django.db import migrations

PLANS = [
    # code, name, price, setup fee, branches, staff, custom domain, white-label
    ("starter", "Starter", 2500, 0, 1, 5, False, False),
    ("growth", "Growth", 6500, 5000, 3, 20, True, False),
    ("business", "Business", 15000, 25000, 0, 0, True, True),
]


def create_plans(apps, schema_editor):
    Plan = apps.get_model("tenants", "Plan")
    for order, (code, name, price, setup, branches, staff, domain, white) in enumerate(PLANS):
        Plan.objects.update_or_create(
            code=code,
            defaults=dict(
                name=name, monthly_price_kes=price, setup_fee_kes=setup, max_branches=branches,
                max_staff=staff, allows_custom_domain=domain, allows_white_label=white, sort_order=order,
            ),
        )


def remove_plans(apps, schema_editor):
    apps.get_model("tenants", "Plan").objects.filter(code__in=[p[0] for p in PLANS], tenants__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("tenants", "0001_initial")]
    operations = [migrations.RunPython(create_plans, remove_plans)]
