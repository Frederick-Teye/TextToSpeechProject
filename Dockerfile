# Stage 1: Builder Stage
# This stage is used to install build-time dependencies and Python packages.
# Using a slim-bookworm image for a smaller footprint.
FROM python:3.11-slim-bookworm as builder

# Set environment variables to prevent Python from writing .pyc files
# and to ensure unbuffered output for immediate logging.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies required for building Python packages like psycopg2-binary (PostgreSQL adapter)
# and other utilities like netcat-openbsd (for health checks/waiting for services).
# 'gettext' is common for Django's internationalization.
# '--no-install-recommends' keeps the image size down.
# 'rm -rf /var/lib/apt/lists/*' cleans up the apt cache after installation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    gcc \
    make \
    libpq-dev \
    netcat-openbsd \
    gettext \
    # Clean up apt cache to keep image size small
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container for subsequent commands.
WORKDIR /app

# Copy the requirements.txt file first.
# This leverages Docker's build cache: if requirements.txt doesn't change,
# this and subsequent RUN commands (pip install) won't re-execute, speeding up builds.
COPY requirements.txt /app/

# Upgrade pip to the latest version.
RUN pip install --upgrade pip

# Install all Python dependencies from requirements.txt.
# '--no-cache-dir' prevents pip from storing downloaded packages, further reducing image size.
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production/Runtime Stage
# This stage creates the final, smaller image by only copying necessary artifacts from the builder stage.
FROM python:3.11-slim-bookworm

# Set environment variables again for the final image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install only the *runtime* system dependencies needed in the final image.
# 'libpq5' is the PostgreSQL client library (runtime, not dev headers).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libpq5 \
    netcat-openbsd \
    gettext \
    # Clean up apt cache
    && rm -rf /var/lib/apt/lists/*

# Set the working directory for the final application.
WORKDIR /app

# Copy only the installed Python packages from the builder stage to the final image.
# This is key for multi-stage builds to keep the final image minimal.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the rest of your application code into the container.
# This step is placed last because application code changes most frequently,
# which would invalidate Docker's cache for subsequent layers.
COPY . /app/

# Expose port 8000. This is informative, telling Docker that the container listens on this port.
# Port mapping to the host is handled in docker-compose.yml.
EXPOSE 8000

# Define the default command to run when the container starts.
# This command starts the Gunicorn WSGI server for your Django application.
# It will be overridden by the 'command' in docker-compose.yml for the 'web' service
# and by the 'celery_worker' service.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "tts_project.wsgi:application"]