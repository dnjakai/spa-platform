"""URLs served on a business's own domain (booking site and dashboard)."""
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("", include("apps.spa.urls_site")),
    path("dashboard/", include("apps.spa.urls_dashboard")),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
