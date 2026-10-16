from django.urls import path

from . import views

app_name = "site"

urlpatterns = [
    path("", views.site_home, name="home"),
    path("book/<int:service_id>/", views.book, name="book"),
    path("booked/<str:ref>/", views.booking_done, name="booking_done"),
]
