# TTS Document Converter - Complete Project Documentation

## Overview

This is a comprehensive Django-based web application that converts documents (PDF, DOCX, Markdown) into natural-sounding audio using AWS Polly text-to-speech service. The application provides a complete document management system with user authentication, sharing capabilities, and audio generation features.

## Project Architecture

### Core Components

1. **Core App** - Foundation and utilities
2. **Users App** - Custom user model and authentication
3. **Landing App** - Homepage and voice selection
4. **Document Processing App** - File upload, parsing, and management
5. **Speech Processing App** - Audio generation and management

### Technology Stack

- **Backend**: Django 5.2.4, Python 3.12
- **Database**: SQLite (development), PostgreSQL (production)
- **Cache**: Redis
- **Task Queue**: Celery + Redis
- **Storage**: AWS S3
- **TTS Service**: AWS Polly
- **Frontend**: Bootstrap 5, HTML5, JavaScript
- **Authentication**: Django Allauth (Google/GitHub OAuth)
- **File Processing**: PyMuPDF, pypandoc, python-docx

## Core App Documentation

### Settings Configuration (`core/settings/`)

#### Base Settings (`base.py`)

- **Security**: SECRET_KEY, ADMINS, ALLOWED_HOSTS
- **Database**: SQLite default, configurable for production
- **Caching**: Redis-based caching with separate databases for sessions and rate limiting
- **AWS Configuration**: S3, Polly, and general AWS settings
- **Celery**: Task queue configuration with timeouts and retry policies
- **Rate Limiting**: django-ratelimit with Redis backend
- **Logging**: Structured logging with sensitive data filtering
- **Authentication**: Django Allauth with social providers
- **File Upload**: Size limits, filename sanitization, and storage backends

#### Environment-Specific Settings

- **Development** (`dev.py`): Debug enabled, local development settings
- **Production** (`prod.py`): Security hardening, production optimizations
- **Celery** (`celery.py`): Periodic task scheduling

### Middleware (`core/middleware.py`)

#### RateLimitMiddleware

- Catches django-ratelimit exceptions
- Returns proper HTTP 429 responses with Retry-After headers
- Logs rate limit violations for monitoring

### Decorators (`core/decorators.py`)

#### Access Control Decorators

- `document_access_required()`: Checks document ownership/sharing permissions
- `page_access_required()`: Checks page-level access permissions
- `audio_generation_allowed()`: Validates audio generation permissions
- `owner_required()`: Simple ownership validation

### Health Checks (`core/health_check.py`)

#### Endpoints

- `/health/live`: Liveness probe (app running status)
- `/health/ready`: Readiness probe (dependencies check)

#### Checks Performed

- Database connectivity
- Cache availability
- Configuration validation

### Security Utilities (`core/security_utils.py`)

#### Safe Error Handling

- `safe_error_response()`: User-safe error responses without sensitive data
- `log_exception_safely()`: Secure exception logging with data sanitization

#### Data Sanitization

- `sanitize_log_value()`: Redacts sensitive fields in logs
- `SensitiveDataFilter`: Logging filter for automatic data sanitization

### Task Utilities (`core/task_utils.py`)

#### Failure Tracking

- `log_task_failure()`: Records task failures to database
- `send_task_failure_email()`: Admin notifications for task failures
- `get_recent_failures()`: Analytics for failure monitoring

## Users App Documentation

### Custom User Model (`users/models.py`)

#### CustomUser

- Extends AbstractUser
- Email-based authentication (USERNAME_FIELD = "email")
- Voice preference storage (preferred_voice_id)
- Standard Django user fields plus custom voice preference

### Admin Configuration (`users/admin.py`)

- Custom admin interface for user management
- Search and filtering capabilities
- Voice preference display

### Views (`users/views.py`)

- `update_voice_preference()`: AJAX endpoint for voice preference updates
- Validates voice IDs against allowed list
- Updates user profile with selected voice

## Landing App Documentation

### Views (`landing/views.py`)

- `home()`: Homepage with voice selection interface
- Provides standard voice options
- Shows user's current voice preference

### Templates

- `landing/home.html`: Voice selection interface with audio previews
- Interactive voice preview functionality
- Voice preference persistence

## Document Processing App Documentation

### Models (`document_processing/models.py`)

#### Document Model

- User ownership and source type tracking
- File/URL/Text source content storage
- Processing status management
- Error message storage

#### DocumentPage Model

- Page-level content storage (markdown)
- Audio status tracking
- S3 audio file references

#### TaskFailureAlert Model

- Task failure tracking and alerting
- Admin investigation support
- Email notification system

### Forms (`document_processing/forms.py`)

#### DocumentUploadForm

- Multi-source upload support (File/URL/Text)
- File type validation (PDF, DOCX, Markdown)
- Dynamic field visibility based on source type

### Views (`document_processing/views.py`)

#### Document Management

- `document_upload()`: Multi-format document upload with validation
- `document_list_view()`: User's document listing with optimization
- `document_detail()`: Document viewing with page display
- `page_detail()`: Individual page viewing with navigation

#### API Endpoints

- `document_status_api()`: Processing status polling
- `page_edit()`: Markdown content editing with validation
- `render_markdown()`: Live markdown preview
- `document_delete()`: Secure document deletion with confirmation

### Utils (`document_processing/utils.py`)

#### File Handling

- `sanitize_filename()`: Security-focused filename sanitization
- `upload_to_s3()`: Secure S3 upload with unique keys
- `validate_markdown()`: Content security validation
- `sanitize_markdown()`: Safe markdown processing

### Tasks (`document_processing/tasks.py`)

#### Document Processing

- `parse_document_task()`: Background document parsing
- Supports PDF, DOCX, Markdown, URL, and text sources
- Error handling and status management
- Markdown validation and sanitization

### Storage (`document_processing/storage_backends.py`)

- Custom S3 storage backend with security settings
- File overwrite prevention
- Cache control headers

## Speech Processing App Documentation

### Models (`speech_processing/models.py`)

#### Audio Model

- Audio file metadata and status tracking
- Voice uniqueness constraints per page
- Lifetime management (active/deleted/expired)
- S3 key storage and URL generation

#### DocumentSharing Model

- Document sharing with permission levels
- Access control for collaborators

#### AudioAccessLog Model

- Comprehensive audit logging
- Action tracking (generate, play, download, share)
- Security monitoring

#### SiteSettings Model

- Global configuration management
- Singleton pattern for site-wide settings
- Audio retention and notification settings

#### AdminAuditLog Model

- Administrative action tracking
- Security audit trail

### Services (`speech_processing/services.py`)

#### PollyService

- AWS Polly integration for TTS
- Text chunking for long content
- Audio merging and S3 upload
- Error handling and retry logic

#### AudioGenerationService

- Business logic for audio generation
- Permission checking and quota enforcement
- Database transaction management
- Presigned URL generation

### Tasks (`speech_processing/tasks.py`)

#### Audio Generation

- `generate_audio_task()`: Background audio generation
- Text normalization for TTS
- Error handling and retry logic
- Status updates and logging

#### Maintenance Tasks

- `export_audit_logs_to_s3()`: Monthly audit log export
- `check_expired_audios()`: Daily expiry management

### Views (`speech_processing/views.py`)

- Audio generation endpoints
- Permission validation
- Status checking and downloads

### Dashboard (`speech_processing/dashboard_views.py`)

- Administrative analytics interface
- User activity monitoring
- System health reporting

## Template Documentation

### Base Template (`templates/base.html`)

- Bootstrap 5 dark theme
- Responsive navigation
- Message display system
- CSRF token utilities
- Password visibility toggles

### Landing Templates

- Voice selection interface
- Audio preview functionality
- Feature showcase

### Document Processing Templates

- Upload forms with validation
- Document listing and management
- Page viewing and editing
- Sharing interfaces

### Account Templates

- Authentication forms
- Profile management
- Email verification

## Data Flow Architecture

### Document Upload Flow

1. User uploads file via web interface
2. File validated and sanitized
3. Uploaded to S3 with unique key
4. Background task processes document
5. Pages extracted and stored as markdown
6. Status updated for user feedback

### Audio Generation Flow

1. User requests audio for page
2. Permission and quota checks
3. Audio record created with PENDING status
4. Background task generates audio via Polly
5. Audio chunks merged and uploaded to S3
6. Status updated to COMPLETED

### Sharing Flow

1. Document owner creates sharing link
2. Permission level assigned (view/edit/share)
3. Shared user can access document
4. Access logged for audit trail

## Security Features

### Authentication & Authorization

- Email-based authentication
- Social OAuth (Google, GitHub)
- Role-based permissions
- Document-level sharing controls

### Data Protection

- Sensitive data sanitization in logs
- Secure file upload validation
- CSRF protection
- Rate limiting

### Audit & Monitoring

- Comprehensive logging
- Task failure tracking
- Admin audit trails
- Health check endpoints

## Performance Optimizations

### Database

- Query optimization with select_related/prefetch_related
- Index optimization
- Connection pooling

### Caching

- Redis-based caching
- Template fragment caching
- Session storage in Redis

### Background Processing

- Celery task queue
- Configurable timeouts and retries
- Error recovery mechanisms

## Deployment & Operations

### Docker Support

- Multi-stage Dockerfile
- Development and production configurations
- docker-compose orchestration

### Monitoring

- Health check endpoints
- Task failure alerts
- Performance metrics
- Error tracking

### Maintenance

- Automated cleanup tasks
- Audit log exports
- Expiry management
- Database maintenance

## Configuration Management

### Environment Variables

- AWS credentials and configuration
- Database connection strings
- Redis URLs
- Email settings
- Social OAuth keys

### Settings Hierarchy

- Base settings (common configuration)
- Environment-specific overrides
- Runtime configuration via SiteSettings model

## API Reference

### REST Endpoints

- Document CRUD operations
- Audio generation and management
- User preference updates
- Status polling APIs

### Background Tasks

- Document processing tasks
- Audio generation tasks
- Maintenance and cleanup tasks
- Audit and reporting tasks

## Future Enhancements

### Potential Features

- Batch document processing
- Advanced sharing controls
- Custom voice training
- Real-time collaboration
- Mobile app companion
- Integration APIs

### Scalability Improvements

- CDN integration
- Database sharding
- Microservices architecture
- Advanced caching strategies

This documentation provides a complete overview of the TTS Document Converter application, covering all major components, data flows, security features, and operational aspects.
