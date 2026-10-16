"""URLs for the platform's own domain: landing page and the owner admin."""
from django.contrib import admin
from django.urls import path

from apps.tenants import views as tenant_views

admin.site.site_header = "Platform console"
admin.site.site_title = "Platform console"
admin.site.index_title = "Manage businesses, plans and domains"

urlpatterns = [
    path("", tenant_views.platform_home, name="platform_home"),
    path("admin/", admin.site.urls),
]
