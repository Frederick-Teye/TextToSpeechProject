import os

# Load base settings first
from .base import *

# Determine environment and load specific settings
# Default to 'dev' settings if DJANGO_SETTINGS_MODULE is not explicitly set
ENVIRONMENT = os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.dev")

if "dev" in ENVIRONMENT:
    from .dev import *
elif "production" in ENVIRONMENT:
    from .production import *
# Add other environments (e.g., 'staging') here as needed
