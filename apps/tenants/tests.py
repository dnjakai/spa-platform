from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.spa.models import Branch, Service
from apps.tenants.context import tenant_context
from apps.tenants.models import Domain, Plan, Tenant, TenantMembership
from apps.tenants.services import provision_tenant


@override_settings(PLATFORM_DOMAIN="localhost")
class ProvisioningTests(TestCase):
    def test_provision_creates_everything_a_business_needs(self):
        result = provision_tenant(
            name="Amani Day Spa", slug="amani", owner_email="Owner@Amani.test", plan_code="growth", password="x-123456"
        )
        t = result.tenant
        self.assertEqual(t.status, Tenant.Status.TRIAL)
        self.assertIsNotNone(t.trial_ends_on)
        self.assertEqual(t.primary_host, "amani.localhost")
        self.assertTrue(Domain.objects.get(domain="amani.localhost").is_primary)
        self.assertEqual(result.owner.email, "owner@amani.test")
        self.assertEqual(TenantMembership.objects.get(tenant=t).role, "owner")
        with tenant_context(t):
            self.assertEqual(Branch.objects.count(), 1)
            self.assertGreater(Service.objects.count(), 3)
        self.assertTrue(t.tagline)

    def test_existing_user_is_reused_as_owner(self):
        a = provision_tenant(name="Spa A", slug="spa-a", owner_email="same@x.test")
        b = provision_tenant(name="Spa B", slug="spa-b", owner_email="same@x.test")
        self.assertEqual(a.owner.pk, b.owner.pk)
        self.assertIsNone(b.temporary_password)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_reserved_and_invalid_slugs_are_rejected(self):
        for bad in ["admin", "www", "a", "Has Space", "-dash"]:
            with self.assertRaises(ValidationError, msg=bad):
                provision_tenant(name="Bad", slug=bad, owner_email=f"{len(bad)}@x.test")

    def test_starter_menu_matches_business_type(self):
        t = provision_tenant(name="Kinyozi", slug="kinyozi", owner_email="k@x.test", business_type="barbershop").tenant
        with tenant_context(t):
            self.assertTrue(Service.objects.filter(name="Haircut").exists())

    def test_create_tenant_command(self):
        call_command("create_tenant", "Lulu Nails", "lulu", "lulu@x.test", "--plan", "starter", "--type", "nail_bar",
                     stdout=open("/dev/null", "w"))
        self.assertTrue(Tenant.objects.filter(slug="lulu", business_type="nail_bar").exists())


@override_settings(PLATFORM_DOMAIN="localhost")
class TenantIsolationTests(TestCase):
    def setUp(self):
        self.a = provision_tenant(name="Spa A", slug="spa-a", owner_email="a@x.test").tenant
        self.b = provision_tenant(name="Spa B", slug="spa-b", owner_email="b@x.test").tenant

    def test_objects_manager_only_sees_the_current_tenant(self):
        with tenant_context(self.a):
            a_ids = set(Service.objects.values_list("tenant_id", flat=True))
        self.assertEqual(a_ids, {self.a.pk})
        # Outside a tenant (platform admin) everything is visible.
        self.assertEqual(set(Service.objects.values_list("tenant_id", flat=True)), {self.a.pk, self.b.pk})

    def test_cannot_save_a_row_for_another_tenant(self):
        with tenant_context(self.a):
            with self.assertRaises(ValidationError):
                Service(tenant=self.b, name="Sneaky", price_kes=1).save()

    def test_save_without_any_tenant_is_refused(self):
        with self.assertRaises(ValidationError):
            Service(name="Orphan", price_kes=1).save()


@override_settings(PLATFORM_DOMAIN="localhost")
class MiddlewareTests(TestCase):
    def setUp(self):
        self.amani = provision_tenant(name="Amani", slug="amani", owner_email="o@amani.test", plan_code="growth").tenant
        self.lulu = provision_tenant(name="Lulu", slug="lulu", owner_email="o@lulu.test", plan_code="starter").tenant

    def test_platform_host_serves_landing_page(self):
        response = self.client.get("/", HTTP_HOST="localhost")
        self.assertContains(response, "Platform console")

    def test_subdomain_serves_that_business(self):
        response = self.client.get("/", HTTP_HOST="amani.localhost")
        self.assertContains(response, "Amani")
        self.assertNotContains(response, "Lulu")

    def test_unknown_host_is_404(self):
        self.assertEqual(self.client.get("/", HTTP_HOST="nobody.localhost").status_code, 404)
        self.assertEqual(self.client.get("/", HTTP_HOST="evil.example.com").status_code, 404)

    def test_custom_domain_serves_business(self):
        Domain.objects.create(tenant=self.amani, domain="book.amanispa.co.ke")
        response = self.client.get("/", HTTP_HOST="book.amanispa.co.ke")
        self.assertContains(response, "Amani")

    def test_custom_domain_redirects_when_plan_no_longer_allows_it(self):
        Domain.objects.create(tenant=self.amani, domain="book.amanispa.co.ke")
        self.amani.plan = Plan.objects.get(code="starter")
        self.amani.save()
        response = self.client.get("/book/1/", HTTP_HOST="book.amanispa.co.ke")
        self.assertEqual(response.status_code, 302)
        self.assertIn("amani.localhost", response["Location"])

    def test_suspended_business_is_offline(self):
        self.lulu.status = Tenant.Status.SUSPENDED
        self.lulu.save()
        self.assertEqual(self.client.get("/", HTTP_HOST="lulu.localhost").status_code, 403)

    def test_admin_only_exists_on_platform_host(self):
        self.assertEqual(self.client.get("/admin/", HTTP_HOST="amani.localhost").status_code, 404)
        self.assertEqual(self.client.get("/admin/", HTTP_HOST="localhost").status_code, 302)

    def test_powered_by_hidden_only_on_white_label_plan(self):
        self.assertContains(self.client.get("/", HTTP_HOST="lulu.localhost"), "Powered by")
        self.lulu.plan = Plan.objects.get(code="business")
        self.lulu.save()
        self.assertNotContains(self.client.get("/", HTTP_HOST="lulu.localhost"), "Powered by")

    def test_starter_plan_cannot_add_custom_domain(self):
        d = Domain(tenant=self.lulu, domain="lulunails.co.ke")
        with self.assertRaises(ValidationError):
            d.full_clean()


@override_settings(PLATFORM_DOMAIN="localhost")
class PlatformAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("admin", "admin@p.test", "pw-123456")
        self.client.force_login(self.admin)

    def test_admin_add_tenant_bootstraps_it(self):
        response = self.client.post(
            reverse("admin:tenants_tenant_add"),
            {
                "name": "Serene Touch Spa", "slug": "serene", "business_type": "spa",
                "plan": Plan.objects.get(code="growth").pk, "status": "trial", "city": "Nairobi",
                "brand_color": "#0f766e", "font_style": "classic", "sold_by": "",
                "owner_email": "owner@serene.test", "owner_first_name": "Wanjiru", "owner_last_name": "K",
                "owner_phone": "0712345678",
            },
            HTTP_HOST="localhost",
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        tenant = Tenant.objects.get(slug="serene")
        self.assertTrue(tenant.domains.filter(domain="serene.localhost").exists())
        self.assertTrue(TenantMembership.objects.filter(tenant=tenant, user__email="owner@serene.test", role="owner").exists())
        self.assertContains(response, "temporary password")
        with tenant_context(tenant):
            self.assertTrue(Service.objects.exists())

    def test_admin_lists_all_tenants(self):
        provision_tenant(name="One", slug="one", owner_email="1@x.test")
        provision_tenant(name="Two", slug="two", owner_email="2@x.test")
        response = self.client.get(reverse("admin:tenants_tenant_changelist"), HTTP_HOST="localhost")
        self.assertContains(response, "One")
        self.assertContains(response, "Two")

    def test_non_staff_cannot_open_console(self):
        self.client.logout()
        owner = provision_tenant(name="X", slug="xspa", owner_email="x@x.test", password="pw-123456").owner
        self.client.force_login(owner)
        response = self.client.get(reverse("admin:tenants_tenant_changelist"), HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 302)
