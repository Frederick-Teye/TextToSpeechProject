from django.shortcuts import render
from django.conf import settings


def home(request):
    STANDARD_VOICES = [
        ("Joanna", "Joanna (English US)"),
        ("Matthew", "Matthew (English US)"),
        ("Salli", "Salli (English US)"),
        ("Kimberly", "Kimberly (English US)"),
        ("Kendra", "Kendra (English US)"),
        ("Justin", "Justin (English US)"),
        ("Joey", "Joey (English US)"),
        ("Ivy", "Ivy (English US)"),
    ]

    # Get user's preferred voice if authenticated
    preferred_voice = None
    if request.user.is_authenticated and hasattr(request.user, "preferred_voice_id"):
        preferred_voice = request.user.preferred_voice_id

    context = {
        "standard_voices": STANDARD_VOICES,
        "preferred_voice": preferred_voice,
    }
    return render(request, "landing/home.html", context)


def about(request):
    """About page explaining the app features and cost-saving sharing strategy."""
    context = {
        "linkedin_url": "https://www.linkedin.com/in/frederick-teye-61627b248/",
    }
    return render(request, "landing/about.html", context)
