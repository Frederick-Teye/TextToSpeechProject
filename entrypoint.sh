#!/bin/sh

# entrypoint.sh

# This script waits for the database to be ready and then runs the main application command.

# The host and port for the database are read from environment variables.
# We use the values from your .env file.
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

echo "Waiting for database at $DB_HOST:$DB_PORT..."

# We use netcat (nc) to check if the port is open.
# The Dockerfile already installs netcat-traditional for us.
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.1 # wait for 1/10 of a second before check again
done

echo "Database started"

# Wait for Redis
echo "Waiting for Redis at redis:6379..."
while ! nc -z redis ${REDIS_PORT}; do
  sleep 0.1
done
echo "Redis started"

# Now that the database is ready, run the Django commands
echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn server..."
exec gunicorn tts_project.wsgi:application --bind 0.0.0.0:8000 --timeout 240