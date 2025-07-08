from django.shortcuts import render
from django.http import HttpResponse


def home(request):
    # A simple placeholder view function
    return HttpResponse("Hello from the TTS Project Core App!")
