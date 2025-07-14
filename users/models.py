from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Custom User Model.
    We are extending the default user to allow for future customization.
    The email field will be used for login instead of the username.
    """

    # We are overriding the default email field to make it unique,
    # as this will be our main identifier for users.
    email = models.EmailField(unique=True, verbose_name="email address")

    # Tell Django that the `email` field is the "username" for logging in.
    USERNAME_FIELD = "email"

    # The `createsuperuser` command will ask for these fields.
    # We still need a username for Django's internals, but it's not for login.
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email
