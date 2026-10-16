from django.conf import settings


def tenant(request):
    current = getattr(request, "tenant", None)
    return {
        "tenant": current,
        "platform_name": settings.PLATFORM_NAME,
        "platform_domain": settings.PLATFORM_DOMAIN,
        "brand_color": current.brand_color if current else "#2b54c4",
    }
