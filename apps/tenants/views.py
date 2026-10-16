from django.shortcuts import render

from .models import Plan, Tenant


def platform_home(request):
    """Landing page on the platform domain."""
    live = Tenant.objects.exclude(status__in=[Tenant.Status.SUSPENDED, Tenant.Status.CHURNED])
    return render(
        request,
        "platform/home.html",
        {"plans": Plan.objects.all(), "tenant_count": live.count()},
    )
