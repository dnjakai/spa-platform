from datetime import datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.tenants.models import TenantMembership

from .forms import BookingForm, BrandingForm
from .models import Booking, Branch, Service, StaffMember
from .payments import request_deposit


# --------------------------------------------------------------------------
# Public booking site (on the business's own address)
# --------------------------------------------------------------------------
def site_home(request):
    return render(request, "site/home.html", {
        "services": Service.objects.filter(is_active=True),
        "branches": Branch.objects.filter(is_active=True),
    })


def book(request, service_id):
    # Service.objects is scoped to this business, so another business's
    # service id simply 404s here.
    service = get_object_or_404(Service, pk=service_id, is_active=True)
    form = BookingForm(request.POST or None, service=service)
    if request.method == "POST" and form.is_valid():
        booking = form.save()
        stk = request_deposit(booking)
        request.session["last_booking_ref"] = booking.ref
        messages.info(request, stk.message)
        return redirect("site:booking_done", ref=booking.ref)
    return render(request, "site/book.html", {"service": service, "form": form})


def booking_done(request, ref):
    # Only the browser that made the booking can see its confirmation page.
    if request.session.get("last_booking_ref") != ref:
        raise Http404
    booking = get_object_or_404(Booking.objects.select_related("service", "branch", "customer"), ref=ref)
    return render(request, "site/done.html", {"booking": booking})


# --------------------------------------------------------------------------
# Business dashboard (staff of this business only)
# --------------------------------------------------------------------------
def membership_required(*roles):
    """Allow only signed-in users with an active membership of this business."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            membership = TenantMembership.objects.filter(
                tenant=request.tenant, user=request.user, is_active=True
            ).first()
            if membership is None or (roles and membership.role not in roles):
                return render(request, "dashboard/no_access.html", status=403)
            request.membership = membership
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


@membership_required()
def dashboard_home(request):
    tenant = request.tenant
    today = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    todays = Booking.objects.filter(start__gte=day_start, start__lt=day_start + timedelta(days=1)).select_related(
        "customer", "service", "branch", "staff"
    )
    taken = (
        todays.filter(status=Booking.Status.COMPLETED).aggregate(total=Sum("price_kes"))["total"] or 0
    ) + (todays.exclude(status=Booking.Status.COMPLETED).exclude(mpesa_receipt="").aggregate(
        total=Sum("deposit_kes"))["total"] or 0)
    plan = tenant.plan
    return render(request, "dashboard/home.html", {
        "bookings": todays,
        "upcoming_count": Booking.objects.filter(start__gte=timezone.now()).exclude(
            status__in=[Booking.Status.CANCELLED, Booking.Status.NO_SHOW]).count(),
        "taken_today": taken,
        "usage": [
            ("Branches", Branch.objects.count(), plan.max_branches),
            ("Staff", StaffMember.objects.filter(is_active=True).count(), plan.max_staff),
        ],
        "statuses": Booking.Status,
        "can_edit_branding": request.membership.role in {TenantMembership.Role.OWNER, TenantMembership.Role.MANAGER},
    })


NEXT_STATUS = {
    "confirm": Booking.Status.CONFIRMED,
    "arrive": Booking.Status.ARRIVED,
    "complete": Booking.Status.COMPLETED,
    "no_show": Booking.Status.NO_SHOW,
    "cancel": Booking.Status.CANCELLED,
}


@require_POST
@membership_required()
def booking_action(request, ref, action):
    booking = get_object_or_404(Booking, ref=ref)
    if action not in NEXT_STATUS:
        raise Http404
    booking.status = NEXT_STATUS[action]
    booking.save(update_fields=["status"])
    messages.success(request, f"{booking.customer.name}: {booking.get_status_display().lower()}.")
    return redirect("dashboard:home")


@membership_required(TenantMembership.Role.OWNER, TenantMembership.Role.MANAGER)
def branding(request):
    form = BrandingForm(request.POST or None, request.FILES or None, instance=request.tenant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Branding saved. Your booking site is updated.")
        return redirect("dashboard:branding")
    return render(request, "dashboard/branding.html", {"form": form})
