web: gunicorn tts_project.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A tts_project worker -l info