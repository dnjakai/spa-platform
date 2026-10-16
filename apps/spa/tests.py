from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.tenants.context import tenant_context
from apps.tenants.models import Plan, TenantMembership
from apps.tenants.services import provision_tenant

from .models import Booking, Branch, Customer, Service


def tomorrow_at(hour):
    return (timezone.localdate() + timedelta(days=1)).isoformat(), f"{hour:02d}:00"


@override_settings(PLATFORM_DOMAIN="localhost")
class BookingSiteTests(TestCase):
    def setUp(self):
        self.amani = provision_tenant(name="Amani", slug="amani", owner_email="o@amani.test").tenant
        self.other = provision_tenant(name="Other", slug="other", owner_email="o@other.test").tenant
        with tenant_context(self.amani):
            self.service = Service.objects.first()
            self.branch = Branch.objects.first()
        with tenant_context(self.other):
            self.other_service = Service.objects.first()

    def post_booking(self, service, host="amani.localhost", hour=11, phone="0712 345 678"):
        day, at = tomorrow_at(hour)
        return self.client.post(
            f"/book/{service.pk}/",
            {"branch": self.branch.pk, "date": day, "time": at, "name": "Grace Wambui", "phone": phone, "consent": "on"},
            HTTP_HOST=host,
        )

    def test_customer_can_book_online(self):
        response = self.post_booking(self.service)
        self.assertEqual(response.status_code, 302)
        booking = Booking.all_objects.get()
        self.assertEqual(booking.tenant, self.amani)
        self.assertEqual(booking.customer.phone, "0712345678")
        self.assertEqual(booking.deposit_kes, self.service.deposit_kes)
        self.assertEqual(booking.end - booking.start, timedelta(minutes=self.service.duration_minutes))
        done = self.client.get(response["Location"], HTTP_HOST="amani.localhost")
        self.assertContains(done, booking.ref)

    def test_cannot_book_another_businesss_service(self):
        response = self.client.get(f"/book/{self.other_service.pk}/", HTTP_HOST="amani.localhost")
        self.assertEqual(response.status_code, 404)

    def test_booking_outside_opening_hours_is_rejected(self):
        response = self.post_booking(self.service, hour=20)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is open")
        self.assertFalse(Booking.all_objects.exists())

    def test_invalid_phone_is_rejected(self):
        response = self.post_booking(self.service, phone="12345")
        self.assertContains(response, "Kenyan mobile number")

    def test_same_phone_is_separate_customer_per_business(self):
        Customer.all_objects.create(tenant=self.other, name="Grace", phone="0712345678")
        self.post_booking(self.service)
        self.assertEqual(Customer.all_objects.filter(phone="0712345678").count(), 2)

    def test_confirmation_page_is_private_to_the_booker(self):
        response = self.post_booking(self.service)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(response["Location"], HTTP_HOST="amani.localhost").status_code, 404)


@override_settings(PLATFORM_DOMAIN="localhost")
class DashboardTests(TestCase):
    def setUp(self):
        r = provision_tenant(name="Amani", slug="amani", owner_email="o@amani.test", password="pw-123456")
        self.amani, self.owner = r.tenant, r.owner
        other = provision_tenant(name="Other", slug="other", owner_email="o@other.test", password="pw-123456")
        self.stranger = other.owner

    def test_login_required(self):
        response = self.client.get("/dashboard/", HTTP_HOST="amani.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_owner_can_sign_in_and_see_dashboard(self):
        self.client.post("/accounts/login/", {"username": "o@amani.test", "password": "pw-123456"},
                         HTTP_HOST="amani.localhost")
        response = self.client.get("/dashboard/", HTTP_HOST="amani.localhost")
        self.assertContains(response, "appointments")

    def test_owner_of_another_business_is_refused(self):
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get("/dashboard/", HTTP_HOST="amani.localhost").status_code, 403)

    def test_receptionist_cannot_change_branding(self):
        from django.contrib.auth import get_user_model
        rec = get_user_model().objects.create_user("rec@amani.test", "rec@amani.test", "pw-123456")
        TenantMembership.objects.create(tenant=self.amani, user=rec, role="receptionist")
        self.client.force_login(rec)
        self.assertEqual(self.client.get("/dashboard/", HTTP_HOST="amani.localhost").status_code, 200)
        self.assertEqual(self.client.get("/dashboard/branding/", HTTP_HOST="amani.localhost").status_code, 403)

    def test_owner_updates_branding(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/dashboard/branding/",
            {"name": "Amani Spa & Wellness", "brand_color": "#123456", "font_style": "classic",
             "tagline": "Relax", "contact_phone": "", "contact_email": ""},
            HTTP_HOST="amani.localhost",
        )
        self.assertEqual(response.status_code, 302)
        self.amani.refresh_from_db()
        self.assertEqual(self.amani.brand_color, "#123456")
        self.assertContains(self.client.get("/", HTTP_HOST="amani.localhost"), "#123456")

    def test_custom_domain_needs_growth_plan(self):
        self.client.force_login(self.owner)
        data = {"name": "Amani", "brand_color": "#123456", "font_style": "modern", "tagline": "",
                "contact_phone": "", "contact_email": "", "custom_domain": "book.amani.co.ke"}
        self.client.post("/dashboard/branding/", data, HTTP_HOST="amani.localhost")
        self.assertFalse(self.amani.domains.filter(domain="book.amani.co.ke").exists())  # disabled on Starter
        self.amani.plan = Plan.objects.get(code="growth")
        self.amani.save()
        self.client.post("/dashboard/branding/", data, HTTP_HOST="amani.localhost")
        self.assertTrue(self.amani.domains.filter(domain="book.amani.co.ke", is_custom=True).exists())

    def test_booking_status_actions(self):
        with tenant_context(self.amani):
            customer = Customer.objects.create(name="Mary", phone="0722118204")
            booking = Booking.objects.create(
                customer=customer, service=Service.objects.first(), branch=Branch.objects.first(),
                start=timezone.now() + timedelta(hours=1),
            )
        self.client.force_login(self.owner)
        self.client.post(f"/dashboard/bookings/{booking.ref}/confirm/", HTTP_HOST="amani.localhost")
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)


@override_settings(PLATFORM_DOMAIN="localhost")
class PlanLimitTests(TestCase):
    def test_starter_allows_one_branch(self):
        t = provision_tenant(name="Small", slug="small", owner_email="s@x.test", plan_code="starter").tenant
        with tenant_context(t):
            extra = Branch(tenant=t, name="Second")
            with self.assertRaises(ValidationError):
                extra.full_clean()

    def test_business_plan_is_unlimited(self):
        t = provision_tenant(name="Big", slug="big", owner_email="b@x.test", plan_code="business").tenant
        with tenant_context(t):
            for i in range(5):
                b = Branch(tenant=t, name=f"Branch {i}")
                b.full_clean()
                b.save()
            self.assertEqual(Branch.objects.count(), 6)
