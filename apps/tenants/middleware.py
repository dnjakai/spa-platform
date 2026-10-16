from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render

from .context import reset_current_tenant, set_current_tenant
from .models import Domain


def platform_hosts():
    base = settings.PLATFORM_DOMAIN
    extra = getattr(settings, "PLATFORM_EXTRA_HOSTS", ["127.0.0.1", "testserver"])
    return {base, f"www.{base}", *extra}


class TenantMiddleware:
    """
    Works out which business a request is for, from the host name alone.

    - The platform domain (and www.) → owner admin and landing page, no tenant.
    - <slug>.<platform domain> or a verified custom domain → that tenant; its
      booking site and dashboard URLs are used and all tenant-scoped queries
      are filtered to it.
    - Anything else → 404, so ALLOWED_HOSTS can be a wildcard.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower().rstrip(".")
        request.tenant = None

        if host in platform_hosts():
            return self.get_response(request)

        domain = Domain.objects.select_related("tenant", "tenant__plan").filter(domain=host).first()
        if domain is None:
            raise Http404("No business is set up at this address.")

        tenant = domain.tenant
        # A custom domain only works while the plan includes it; otherwise send
        # visitors to the free subdomain instead of showing a broken site.
        if domain.is_custom and not tenant.plan.allows_custom_domain:
            return HttpResponseRedirect(f"{request.scheme}://{tenant.subdomain}{self._port(request)}{request.get_full_path()}")

        if not tenant.is_live:
            return render(request, "site/unavailable.html", {"tenant": tenant}, status=403)

        request.tenant = tenant
        request.urlconf = settings.TENANT_URLCONF
        token = set_current_tenant(tenant)
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant(token)

    @staticmethod
    def _port(request):
        port = request.get_port()
        return "" if port in {"80", "443"} else f":{port}"
