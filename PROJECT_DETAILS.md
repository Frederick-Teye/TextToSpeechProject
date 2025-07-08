# Project Details: Text-to-Speech Document Converter

This document provides in-depth details about the architecture, project structure, setup, and key decisions made for the Text-to-Speech Document Converter application. It complements the `README.md` by offering more technical specifics.

---

## 1. Project Overview & Core Functionality

The TTS Document Converter is a Django web application designed to transform various document types and web content into audible speech using AWS Polly.

- **Input Formats:** Users can upload PDF files, Microsoft Word (.docx) files, existing Markdown files, or provide URLs of webpages.
- **Standardized Content Storage:** All input content is first processed and converted into a **standardized Markdown format**. This Markdown content is then stored in the PostgreSQL database, logically divided into "pages" or sections (e.g., one Markdown entry per PDF page or coherent webpage section).
- **Text-to-Speech (TTS) Processing:**
  - **Polly Input:** Critically, before sending text to AWS Polly for speech synthesis, the stored **Markdown content will be programmatically converted to plain text (stripping all Markdown syntax)**. AWS Polly requires plain text or SSML (Speech Synthesis Markup Language); it does not interpret Markdown.
  - The generated MP3 audio files are then stored on AWS S3.
- **Audio Playback & Text Display:**
  - Users can access their processed documents and play the generated audio for each page.
  - The audio will **stream progressively** from AWS S3 via standard HTML `<audio>` tags.
  - The corresponding Markdown text (retrieved from the database) is dynamically rendered as HTML and displayed on the screen. Users can manually scroll and follow along while listening. Real-time word-by-word synchronization is explicitly _not_ implemented to simplify initial development, focusing on core functionality.
- **User Management:** User authentication is handled robustly via `django-allauth`, supporting traditional email/password registration and social logins (e.g., Google).
- **Asynchronous Processing:** All long-running tasks (such as document parsing, Markdown conversion, plain text extraction for Polly, TTS generation, and S3 uploads) are offloaded to **Celery asynchronous tasks**. This ensures the web application remains responsive and provides a smooth user experience by preventing blocking operations on the main web server.
- **Local Development Parity:** The local development environment rigorously uses Docker Compose to mirror the production setup (PostgreSQL database, Redis message broker/cache) as closely as possible, minimizing "it works on my machine" issues.

---

## 2. Project Structure (Detailed)

This section describes the purpose and contents of each major file and directory within the project's root.

```
tts_project/
├── .dockerignore                 # Specifies files/directories to exclude from Docker build context (e.g., .env, local media, Git files)
├── .env.example                  # Template for local environment variables, committed to Git
├── .gitignore                    # Specifies files/directories to exclude from Git version control (e.g., .env, venv, local databases)
├── Dockerfile                    # Contains instructions for Docker to build the Python application image (Django/Celery)
├── Procfile                      # Heroku-specific: defines process types (e.g., 'web' for Gunicorn, 'worker' for Celery)
├── README.md                     # High-level project description, quick start guide for new users
├── requirements.txt              # Lists all Python package dependencies with exact pinned versions
├── docker-compose.yml            # Defines and orchestrates the multi-container Docker development environment (web, worker, db, redis)
├── manage.py                     # Django's command-line utility for administrative tasks (migrations, runserver, etc.)
├── PROJECT_DETAILS.md            # This document: in-depth technical details, architecture, and design decisions
│
├── tts_project/                  # Main Django project directory (Python package for core settings, URLs)
│   ├── asgi.py                   # ASGI application entry point (for asynchronous operations, e.g., Django Channels)
│   ├── settings/                 # Directory containing environment-specific Django settings
│   │   ├── init.py           # Makes 'settings' a Python package; dynamically imports dev/prod settings
│   │   ├── base.py               # Contains common Django settings applicable to all environments
│   │   ├── dev.py                # Overrides/adds settings specific to local development (e.g., DEBUG=True, local file storage)
│   │   ├── production.py         # Overrides/adds settings specific to production (Heroku) (e.g., DEBUG=False, S3, security headers)
│   │   └── celery.py             # Configuration for the Celery application instance
│   ├── urls.py                   # Main project URL dispatcher, includes URLs from individual apps
│   └── wsgi.py                   # WSGI application entry point (for synchronous web servers like Gunicorn)
│
├── core/                         # Django app for core functionalities, shared utilities, and base templates
│   ├── migrations/               # Database migration files for models in this app
│   ├── static/                   # Static assets (CSS, JS, images) specific to this app
│   ├── templates/                # HTML template files specific to this app (e.g., for base layout or home page)
│   ├── init.py               # Marks directory as a Python package
│   ├── admin.py                  # Registers models with Django admin interface
│   ├── apps.py                   # App configuration class
│   ├── models.py                 # Database models defined for this app
│   ├── tests.py                  # Unit tests for this app's components
│   ├── urls.py                   # URL patterns specific to this app
│   └── views.py                  # View functions/classes for handling requests in this app
│
├── accounts/                     # Django app for user management, profiles, and django-allauth integration (to be created)
│   └── # ... (will contain standard Django app structure: migrations/, models.py, views.py, urls.py etc.)
│
├── document_processing/          # Django app for handling document/webpage input, parsing, and Markdown conversion (to be created)
│   └── # ... (will contain standard Django app structure, including tasks.py for Celery)
│
├── audio_playback/               # Django app for managing audio playback, text display, and user interfaces (to be created)
│   └── # ... (will contain standard Django app structure)
│
└── media/                        # Local directory for user-uploaded files during development (ignored by Git, S3 in production)
```

---

## 3. Environment Variables (`.env.example` & `.env`)

The project leverages `python-decouple` to manage configuration via environment variables, aligning with The 12-Factor App methodology for flexible and secure deployments across environments.

- **`.env.example` (Committed to Git):** This file serves as a template, listing all expected environment variables with placeholder values. It's crucial documentation for anyone setting up the project.
- **`.env` (Ignored by Git via `.gitignore`):** This file contains the actual, sensitive values for local development (e.g., API keys, database credentials). It's created by copying `.env.example` and filling in local-specific, secret values.

**Key Environment Variables Defined:**

- `DJANGO_SECRET_KEY`: Django's cryptographic secret key, essential for security (must be unique and kept secret).
- `DJANGO_SETTINGS_MODULE`: Specifies which Django settings module to load (e.g., `tts_project.settings.dev` for local development; set to `tts_project.settings.production` on Heroku).
- **Database Configuration (Local PostgreSQL via Docker Compose):**
  - `DB_NAME`, `DB_USER`, `DB_PASSWORD`: Credentials used by the `db` service in `docker-compose.yml` to initialize the PostgreSQL database.
  - `DB_HOST=db`, `DB_PORT=5432`: These define how the `web` and `celery_worker` services connect to the PostgreSQL `db` service within the Docker network.
  - `DATABASE_URL`: A comprehensive database connection string (e.g., `postgres://user:password@host:port/dbname`). Locally, this is constructed in `dev.py` from the `DB_` variables; on Heroku, it's provided directly by the PostgreSQL add-on.
- **Redis Configuration (Celery Message Broker & Cache):**
  - `REDIS_HOST=redis`, `REDIS_PORT=6379`, `REDIS_DB=0`: Define how services connect to the Redis `redis` service within the Docker network.
  - `REDIS_URL`: A full Redis connection string (e.g., `redis://host:port/db_num`). Locally, this is constructed in `base.py` from the `REDIS_` variables; on Heroku, it's provided by the Redis add-on.
- **AWS Credentials (for Polly and S3):**
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: Programmatic access credentials for a dedicated IAM user with limited permissions (least privilege).
  - `AWS_DEFAULT_REGION`: The AWS region where your S3 bucket resides and where AWS Polly operations will be performed (e.g., `us-east-1`).
  - `AWS_STORAGE_BUCKET_NAME`: The unique name of your S3 bucket used for storing project static and media files.

---

## 4. Settings Management (`tts_project/settings/`)

Django's settings are organized into a package (`settings/`) to manage environment-specific configurations cleanly and securely, preventing sensitive production settings from mingling with development ones.

- **`__init__.py`**:
  - Serves as the central entry point for Django's settings.
  - First, it imports all common settings from `base.py`.
  - Then, it checks the `DJANGO_SETTINGS_MODULE` environment variable. Based on its value (e.g., `tts_project.settings.dev` or `tts_project.settings.production`), it dynamically imports and applies settings from either `dev.py` or `production.py`. This ensures the correct configuration is loaded automatically for each environment.
- **`base.py`**:
  - Contains all Django settings that are universal across all deployment environments.
  - **Includes:** `INSTALLED_APPS` (listing all core Django, third-party, and custom applications), `MIDDLEWARE`, `TEMPLATES` configuration, `ROOT_URLCONF` (main URL dispatcher), `WSGI_APPLICATION`, and `ASGI_APPLICATION` entry points.
  - **File Paths:** Defines `STATIC_URL`, `STATIC_ROOT`, `MEDIA_URL`, and `MEDIA_ROOT` for default local file handling.
  - **Django-Allauth:** Contains base configurations for user authentication and social logins.
  - **Celery:** Sets up `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND` by retrieving `REDIS_URL` from the environment. This ensures Celery can connect to Redis.
  - **AWS Integration:** Configures `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, and `AWS_S3_REGION_NAME` using `python-decouple`.
  - **S3 as Default Storage:** Sets `DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'`, making S3 the default for storing user-uploaded media files in production.
  - **S3 Caching (`AWS_HEADERS`):** Critically, `AWS_HEADERS` is set to `{'Cache-Control': 'public, max-age=1209600'}`. This instructs web browsers to cache files served from S3 (like audio MP3s) for two weeks (1,209,600 seconds). This significantly improves performance for repeat listeners and reduces S3 data transfer costs.
- **`dev.py`**:
  - Specifically configures Django for your local development environment.
  - Imports all settings from `base.py` first.
  - Sets `DEBUG = True`, enabling debugging tools and detailed error pages.
  - Configures `ALLOWED_HOSTS = ['localhost', '127.0.0.1']` for local access.
  - Defines the `DATABASES` dictionary to connect to the local PostgreSQL container (resolved via the `db` service name in Docker Compose). It uses `dj_database_url.parse` to interpret the `DATABASE_URL` from your `.env` file.
  - **Local File Storage Overrides:** Overrides `DEFAULT_FILE_STORAGE` and `STATICFILES_STORAGE` to use Django's local `FileSystemStorage`. This prevents media (user uploads) and static files from being automatically uploaded to S3 during local development, saving time and AWS costs.
- **`production.py`**:
  - Specifically configures Django for the Heroku production deployment environment.
  - Imports all settings from `base.py` first.
  - Sets `DEBUG = False` (essential for security and performance in production).
  - Ensures `SECRET_KEY` is loaded from Heroku's environment variables.
  - `ALLOWED_HOSTS` is configured to accept the production domain(s) (parsed from a comma-separated environment variable provided by Heroku).
  - `DATABASES` is set up to connect to the Heroku PostgreSQL Add-on, using the `DATABASE_URL` environment variable provided by Heroku.
  - `STATICFILES_STORAGE` is set to `whitenoise.storage.CompressedManifestStaticFilesStorage` for efficient serving of static files on Heroku.
  - **Comprehensive Security Settings:** Includes crucial production-grade security headers and configurations such as `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT` (enforcing HTTPS), `SECURE_HSTS_SECONDS` (HTTP Strict Transport Security), `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` (secure cookies), `X_FRAME_OPTIONS` (clickjacking protection), `SECURE_BROWSER_XSS_FILTER`, and `SECURE_CONTENT_TYPE_NOSNIFF`.
  - **Logging:** Configures basic console logging, allowing Heroku to capture and display application logs effectively.
- **`celery.py`**:
  - Initializes the Celery application instance.
  - Sets the default `DJANGO_SETTINGS_MODULE` so Celery knows which Django settings to use.
  - Configures Celery to pull its specific settings (like broker and result backend URLs) from the Django settings, typically prefixed with `CELERY_`.
  - Enables `app.autodiscover_tasks()`, which automatically finds `@shared_task` functions within your installed Django apps.

---

## 5. Docker Configuration

Docker is an integral part of this project, used for containerizing the application and its dependencies, ensuring consistent development, testing, and deployment environments.

- **`Dockerfile`**:
  - A multi-stage build approach is employed (`FROM python:3.11-slim-bookworm as builder` followed by `FROM python:3.11-slim-bookworm` for the final image). This significantly reduces the final Docker image size by separating build-time tools (like compilers) from runtime necessities.
  - Installs essential system-level dependencies (e.g., `libpq-dev` for PostgreSQL client libraries, `gettext` for Django internationalization) and Python packages from `requirements.txt`.
  - Sets the working directory to `/app` and exposes port `8000` (for the web server).
  - The default `CMD` (command) runs Gunicorn to serve the Django application.
- **`docker-compose.yml`**:
  - Defines the multi-container development application, orchestrating four distinct services:
    - **`web` service**: Represents your Django web application. It builds its image from the `Dockerfile`, mounts your local code into the container for live development, maps host port `8000` to container port `8000`, loads environment variables from `.env`, and waits for the `db` (PostgreSQL) and `redis` services to be ready. Its startup `command` handles `collectstatic`, `migrate`, and then starts `gunicorn`.
    - **`celery_worker` service**: Runs your Celery worker. It uses the same image built from the `Dockerfile`, mounts the local code, loads `.env` variables, and depends on `web` (to ensure migrations are applied) and `redis` (as its message broker). Its `command` specifically starts the Celery worker process by pointing to `tts_project.settings.celery`.
    - **`redis` service**: Utilizes the lightweight `redis:7-alpine` Docker image. It maps port `6379` for optional host access and uses a named volume (`redis_data`) to ensure Redis data persists across container restarts.
    - **`db` service**: Utilizes the lightweight `postgres:15-alpine` Docker image for your local PostgreSQL database. It uses a named volume (`pg_data`) for persistent database storage and initializes the database using environment variables (DB name, user, password) from your `.env` file. It maps port `5432` for optional host access.
  - **Named Volumes (`pg_data`, `redis_data`, `media_data`, `static_data`):** These are defined at the root of the `docker-compose.yml` to ensure that critical data (database, Redis cache, local user uploads, collected static files) persists even if you stop, remove, or recreate your Docker containers.
  - **Custom Network (`app_network`):** All services are connected to a shared internal Docker network, allowing them to communicate with each other using their service names (e.g., the `web` service can connect to the database simply by using `db` as the hostname).

---

## 6. AWS Services Integration

The project integrates with key AWS services for its core functionality and scalability.

- **AWS S3:**
  - Used as the primary storage backend for two main types of files:
    - **User Uploaded Documents:** Original PDF, DOCX, and Markdown files uploaded by users will be stored in a dedicated S3 "folder" (object prefix) like `documents/`.
    - **Generated Audio Files:** MP3 audio files generated by AWS Polly will be stored in a separate S3 "folder" (object prefix) like `audio/`.
  - Configured via `django-storages` which leverages `boto3`.
  - **Caching Strategy:** S3 objects (specifically audio files) are served with `Cache-Control: public, max-age=1209600` headers (2 weeks). This instructs client browsers to aggressively cache these static audio files, significantly improving playback speed for repeat listens and reducing S3 data transfer out costs.
- **AWS Polly:**
  - The core service for converting text into lifelike speech.
  - **Important:** AWS Polly requires plain text or SSML input; it **does not interpret Markdown syntax**. All Markdown content will be stripped down to plain text before being sent to Polly's `SynthesizeSpeech` API.
  - Integrated via the `boto3` SDK within Celery tasks.
- **AWS IAM Security:**
  - Adheres to the principle of **least privilege**.
  - Dedicated **IAM Users** are created for the application (separate for development and production).
  - Custom **IAM Policies** are attached to these users, granting only the minimal necessary permissions to specific S3 buckets (e.g., `s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `s3:DeleteObject` for the specific project buckets) and specific Polly actions (`polly:SynthesizeSpeech`, `polly:DescribeVoices`). This prevents unauthorized access or accidental misuse of AWS resources.
  - Sensitive credentials (Access Key ID and Secret Access Key) are stored as environment variables (`.env` locally, Heroku Config Vars in production) and are never committed to Git.

---
