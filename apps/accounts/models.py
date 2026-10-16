from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    One login per person across the whole platform.

    Platform staff use `is_staff` / `is_superuser` to reach the owner admin.
    Access to a business comes only from a TenantMembership, so the same person
    can, for example, own one spa and work as a receptionist at another.
    """

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, help_text="Kenyan format, e.g. 0712 345 678")

    def __str__(self):
        return self.get_full_name() or self.email
