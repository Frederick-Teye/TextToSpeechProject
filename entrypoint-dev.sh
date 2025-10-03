#!/bin/sh

# Development entrypoint script
# This runs migrations but uses Django dev server instead of Gunicorn

DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}
REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}

echo "Waiting for database at $DB_HOST:$DB_PORT..."
while ! python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1); result = s.connect_ex(('$DB_HOST', $DB_PORT)); s.close(); exit(result)"; do
  sleep 0.1
done
echo "Database started"

echo "Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
while ! python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(1); result = s.connect_ex(('$REDIS_HOST', $REDIS_PORT)); s.close(); exit(result)"; do
  sleep 0.1
done
echo "Redis started"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Django development server..."
exec python manage.py runserver 0.0.0.0:8000
