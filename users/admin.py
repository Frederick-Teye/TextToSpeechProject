from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    # Define which fields to show in the list view of the admin
    list_display = (
        "email",
        "username",
        "is_staff",
        "is_active",
    )
    # Define which fields can be used for searching
    search_fields = (
        "email",
        "username",
    )
    ordering = ("email",)


admin.site.register(CustomUser, CustomUserAdmin)
