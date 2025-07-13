from django.shortcuts import render, redirect
from django.http import HttpResponse
from allauth.account.views import (
    PasswordResetFromKeyView as AllauthPasswordResetFromKeyView,
)
from allauth.account.forms import UserTokenForm, ResetPasswordKeyForm
from django.urls import reverse
import logging  # Import logging module

# Get an instance of a logger for this module
logger = logging.getLogger(__name__)


def home(request):
    """
    A simple placeholder view function for the core app's home page.
    """
    return HttpResponse("Hello from the TTS Project Core App!")


class CustomPasswordResetFromKeyView(AllauthPasswordResetFromKeyView):
    """
    Custom view to handle the password reset from key link.
    This overrides allauth's default behavior to ensure the uidb36 and key
    are correctly processed and passed to the template context,
    and to provide more granular logging for debugging token validation.
    """

    template_name = (
        "account/password_reset_from_key.html"  # Ensure this template exists
    )

    def dispatch(self, request, uidb36, key, *args, **kwargs):
        """
        Handles the initial processing of the password reset link.
        Validates the token and sets necessary attributes on the view instance.
        """
        logger.info(
            f"[{self.__class__.__name__}] Dispatch method called for uidb36={uidb36}, key={key}"
        )
        self.request = request
        self.uidb36 = uidb36  # Store uidb36 on the instance
        self.key = key  # Store key (token) on the instance

        # Attempt to validate the token using allauth's UserTokenForm.
        # This form performs the actual checks for token validity (e.g., expiry, usage).
        token_form = UserTokenForm(data={"uidb36": self.uidb36, "key": self.key})

        if token_form.is_valid():
            # If the token is valid, retrieve the user associated with it.
            # This user object is needed by the ResetPasswordKeyForm.
            self.reset_user = token_form.reset_user
            logger.info(
                f"[{self.__class__.__name__}] Token is valid for user: {self.reset_user.email}"
            )

            # If the token is valid, delegate to the parent class's dispatch method.
            # The parent's dispatch will then call either get() or post() based on the request method.
            # We pass the original URL arguments to super().dispatch for compatibility.
            response = super().dispatch(request, uidb36, key, *args, **kwargs)
            logger.info(
                f"[{self.__class__.__name__}] super().dispatch returned. Response status: {response.status_code}"
            )
            return response
        else:
            # If the token is invalid (e.g., expired, already used, malformed),
            # log the specific errors from the form for debugging.
            logger.warning(
                f"[{self.__class__.__name__}] Token invalid for uidb36={uidb36}, key={key}."
            )
            logger.error(
                f"[{self.__class__.__name__}] UserTokenForm errors: {token_form.errors.as_json()}"
            )

            # Redirect the user to the password reset done page, which typically
            # indicates that the link was invalid or used.
            return redirect(reverse("account_reset_password_from_key_done"))

    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to display the password reset form.
        This method is called by the dispatch method if the token is valid.
        """
        logger.info(
            f"[{self.__class__.__name__}] GET method called. uidb36={self.uidb36}, key={self.key}"
        )

        # Access uidb36 and key from the instance attributes set by dispatch.
        uidb36 = self.uidb36
        key = self.key

        # Instantiate the form that allows the user to enter a new password.
        # It requires the user object and the temporary key for validation.
        form = ResetPasswordKeyForm(user=self.reset_user, temp_key=key)

        logger.info(
            f"[{self.__class__.__name__}] Rendering password reset form template."
        )
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "uidb36": uidb336,  # Pass uidb36 to template context
                "token": key,  # Pass key as 'token' to template context
                "token_valid": True,  # Indicate that the token was valid for this request
            },
        )

    def post(self, request, *args, **kwargs):
        """
        Handles POST requests when the user submits the new password form.
        Validates the new password and updates the user's password.
        """
        logger.info(
            f"[{self.__class__.__name__}] POST method called. uidb36={self.uidb36}, key={self.key}"
        )

        # Access uidb36 and key from the instance attributes set by dispatch.
        uidb36 = self.uidb36
        key = self.key

        # Instantiate the form with the POST data from the user.
        form = ResetPasswordKeyForm(request.POST, user=self.reset_user, temp_key=key)

        if form.is_valid():
            logger.info(
                f"[{self.__class__.__name__}] Password reset form is valid. Saving new password."
            )
            # Save the new password. This method handles hashing and updating the user.
            form.save()
            logger.info(
                f"[{self.__class__.__name__}] Password successfully saved. Redirecting to done page."
            )
            # Redirect to the password reset done page upon successful password change.
            return redirect(reverse("account_reset_password_from_key_done"))
        else:
            logger.warning(
                f"[{self.__class__.__name__}] Password reset form is INVALID. Errors: {form.errors.as_json()}"
            )
            # If the form is invalid, re-render the template with the form errors
            # so the user can correct their input.
            return render(
                request,
                self.template_name,
                {
                    "form": form,
                    "uidb36": uidb36,
                    "token": key,
                    "token_valid": True,  # Token is still valid, but form input has errors
                },
            )
