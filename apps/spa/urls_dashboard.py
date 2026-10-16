from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("bookings/<str:ref>/<str:action>/", views.booking_action, name="booking_action"),
    path("branding/", views.branding, name="branding"),
]
