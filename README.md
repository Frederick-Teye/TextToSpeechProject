# Text-to-Speech Document Converter (TTS-Doc-Converter)

## Project Overview

This project is a web application built with Django that allows users to upload documents (PDF, existing Markdown files) or provide URLs of webpages. The application will process these inputs, **converting all content into a standardized Markdown format**, which is then stored in the database. Each section or "page" of this standardized Markdown content will be transformed into speech using AWS Polly. The resulting audio files will be stored on AWS S3 for efficient and progressive playback.

Users can view a list of their uploaded documents/URLs. When playing a specific document's page, the corresponding Markdown text (rendered as HTML) will be displayed on the screen, allowing the user to manually scroll and follow along while the audio **streams progressively** from S3 via a standard web audio player. The application integrates social authentication via `django-allauth`.

## Core Technologies

- **Backend Framework:** Django
- **Asynchronous Tasks:** Celery
- **Message Broker/Cache:** Redis
- **Database:** PostgreSQL (for both local development and production, via Docker Compose locally)
- **Text-to-Speech & Storage:** AWS Polly, AWS S3
- **Deployment:** Heroku
- **Containerization:** Docker & Docker Compose
- **Environment Management:** `python-decouple`
- **Document Processing:** `pypdf`, `beautifulsoup4`, `html2text`, `lxml`, `Markdown`

## Project Setup (Local Development)

This section will guide you through setting up and running the project on your local machine using Docker Compose.

1.  **Prerequisites:**

    - Docker Desktop (or Docker Engine and Docker Compose) installed on your system.
    - Git installed.
    - An AWS account with configured IAM user credentials (Access Key ID and Secret Access Key) for AWS Polly and S3 access.

2.  **Clone the Repository:**

    ```bash
    git clone [YOUR_GITHUB_REPO_URL_HERE] # Replace with your actual GitHub URL once pushed
    cd tts_project
    ```

3.  **Environment Variables:**
    Create a `.env` file in the project root directory by copying the `.env.example` file:

    ```bash
    cp .env.example .env
    ```

    Then, open `.env` and fill in the required values:

    - `DJANGO_SECRET_KEY`: Generate a strong secret key (e.g., `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`).
    - `AWS_ACCESS_KEY_ID`: Your AWS Access Key ID.
    - `AWS_SECRET_ACCESS_KEY`: Your AWS Secret Access Key.
    - `AWS_STORAGE_BUCKET_NAME`: The name of your S3 bucket for development (e.g., `your-app-dev-s3-bucket`).
    - `AWS_DEFAULT_REGION`: Your preferred AWS region (e.g., `us-east-1`).
    - `DB_NAME`, `DB_USER`, `DB_PASSWORD`: Set these for your local PostgreSQL container (e.g., `mydatabase`, `user`, `password`).
    - `DATABASE_URL` and `REDIS_URL`: These will typically point to the Docker service names for local development.

4.  **Build and Run with Docker Compose:**

    ```bash
    docker compose build
    docker compose up
    ```

5.  **Access the Application:**
    Once the services are up and running, you can access the Django application in your web browser at:
    `http://localhost:8000/`

## Deployment (Heroku)

_(This section will be detailed later)_

## Project Structure

_(This section will be detailed in PROJECT_DETAILS.md)_

## Key Features

- Convert PDF documents to standardized Markdown format.
- Convert webpages to standardized Markdown format.
- Process existing Markdown files into standardized Markdown.
- Text-to-Speech conversion using AWS Polly for processed Markdown content.
- Store generated audio files on AWS S3 for **progressive streaming**.
- User authentication via `django-allauth` (social login).
- User dashboard to manage uploaded files/URLs.
- Display Markdown content (rendered as HTML) alongside an audio player, allowing manual scrolling during playback.

## Contributing

_(To be added later)_

## License

_(To be added later)_

## Contact

_(To be added later)_
