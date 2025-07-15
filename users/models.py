from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse


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

    preferred_voice_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        default="Joanna",
        help_text="The user's preferred AWS Polly voice ID (e.g., 'Joanna').",
    )

    def __str__(self):
        return self.email

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})
