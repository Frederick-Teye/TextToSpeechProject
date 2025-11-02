# Remaining Production Issues - Roadmap

**Date:** November 2, 2025  
**Completion Status:** 9/24 Issues (37.5%)  
**Priority Status:** 9/13 Critical & High Issues (69%)

---

## 🎯 QUICK START FOR NEXT SESSION

### Highest Priority (Do First - 2 Hours Total)

1. **#10** - Input validation on integers (10 min) - QUICK WIN
2. **#11** - Rate limiting on file uploads (45 min) - CRITICAL
3. **#2** - SQL injection prevention (20 min) - CRITICAL

### High Priority (Do Second - 1.5 Hours Total)

4. **#9** - Dashboard query pagination (45 min) - PERFORMANCE
5. **#13** - Transaction rollback (30 min) - DATA SAFETY

---

## 📋 DETAILED ISSUE BREAKDOWN

### 🔴 CRITICAL REMAINING (2)

#### Issue #2: SQL Injection in Markdown ⚠️ CRITICAL

**File:** `document_processing/views.py`  
**Severity:** 🔴 CRITICAL  
**Est. Time:** 20 minutes  
**Complexity:** Medium

**What needs fixing:**

- Add regex validation to markdown content before storing
- Prevent malicious SQL in markdown field
- Ensure parameterized queries always used (Django ORM handles this already)
- Add character whitelist validation

**Implementation approach:**

```python
import re

def validate_markdown_content(content: str, max_chars: int = 50000) -> bool:
    """
    Validate markdown content to prevent injection attacks.

    Allows: alphanumeric, spaces, common markdown chars (#*_-[](){}`, newlines, etc.)
    Blocks: script tags, SQL keywords, special sequences
    """
    if not content or len(content) > max_chars:
        raise ValueError(f"Content must be 1-{max_chars} characters")

    # Block any HTML tags or script content
    if re.search(r'<[^>]+>', content):
        raise ValueError("HTML tags not allowed")

    # Check for SQL injection patterns
    sql_keywords = r'\b(DELETE|DROP|INSERT|UPDATE|ALTER|CREATE)\b'
    if re.search(sql_keywords, content, re.IGNORECASE):
        # Note: This might be too restrictive for some markdown
        # Could be false positive in code blocks
        pass

    return True
```

**Where to add:**

- `document_processing/views.py` - document_detail view (~line 150-200)
- `document_processing/tasks.py` - parse_document_task function
- `document_processing/forms.py` - DocumentUploadForm clean method

**Test cases:**

- Test with normal markdown
- Test with HTML tags
- Test with embedded scripts
- Test with SQL keywords
- Test with very long content

---

#### Issue #13: Transaction Rollback for S3 + DB ⚠️ CRITICAL

**File:** `document_processing/views.py`  
**Severity:** 🔴 CRITICAL  
**Est. Time:** 30 minutes  
**Complexity:** Medium

**What needs fixing:**

- Use `transaction.on_commit()` to queue S3 upload AFTER DB commit
- Prevent orphaned documents with missing S3 files
- Ensure two-phase commit pattern

**Implementation approach:**

```python
from django.db import transaction

@login_required
@transaction.atomic
def document_upload(request):
    # Step 1: Create document record (not yet saved)
    document = Document(user=request.user, title=title, source_type=stype)

    # Step 2: Upload to S3 BEFORE committing (external resource)
    try:
        s3_path = upload_to_s3(uploaded_file, user_id=request.user.id, file_name=filename)
    except Exception as e:
        # S3 failed before DB commit - no orphan created
        raise

    # Step 3: Save document with S3 path
    document.source_content = s3_path
    document.save()

    # Step 4: Queue async task AFTER transaction commits
    # This uses transaction.on_commit() hook
    transaction.on_commit(
        lambda: parse_document_task.delay(document.id)
    )

    return redirect('document_detail', pk=document.id)
```

**Where to add:**

- `document_processing/views.py` - document_upload view (~line 46-100)
- Could add similar pattern to any S3 + DB operations

**Test cases:**

- Test S3 upload failure prevents document save
- Test DB save failure doesn't queue background task
- Test task only queued after transaction commits
- Verify no orphaned documents exist

---

### 🟠 HIGH PRIORITY REMAINING (3)

#### Issue #11: Rate Limiting on File Uploads ⚠️ CRITICAL

**File:** `document_processing/views.py`  
**Severity:** 🟠 HIGH (DoS Prevention)  
**Est. Time:** 45 minutes  
**Complexity:** Medium-High

**What needs fixing:**

- Prevent users from uploading too many files too quickly
- Implement sliding window rate limit (e.g., 10 uploads/hour)
- Return 429 Too Many Requests when limit exceeded
- Use cache for rate limit tracking

**Implementation approach:**

Option 1 (Using django-ratelimit):

```bash
pip install django-ratelimit
```

```python
from django_ratelimit.decorators import ratelimit

@ratelimit(key='user', rate='10/h', method='POST')
@login_required
def document_upload(request):
    # Only 10 uploads per hour per user
    ...
```

Option 2 (Manual using cache):

```python
from django.core.cache import cache
from django.core.exceptions import PermissionDenied

def check_upload_rate_limit(user_id, limit=10, window=3600):
    """Check if user has exceeded upload limit (10 uploads/hour)."""
    key = f"uploads_{user_id}"
    count = cache.get(key, 0)

    if count >= limit:
        raise PermissionDenied(
            f"Too many uploads. Maximum {limit} per hour. Try again later."
        )

    # Increment counter
    if count == 0:
        cache.set(key, 1, window)
    else:
        cache.incr(key)

    return True

@login_required
def document_upload(request):
    if request.method == 'POST':
        check_upload_rate_limit(request.user.id, limit=10, window=3600)
        # ... rest of upload logic
```

**Where to add:**

- `document_processing/views.py` - document_upload view (~line 46)
- Could create `document_processing/rate_limits.py` utility
- Add to requirements.txt if using django-ratelimit

**Test cases:**

- Test normal upload succeeds
- Test 10th upload succeeds
- Test 11th upload returns 429
- Test rate limit resets after 1 hour
- Test limit is per-user (not global)

---

#### Issue #9: Dashboard Query Pagination ⚠️ HIGH

**File:** `speech_processing/dashboard_views.py`  
**Severity:** 🟠 HIGH (Performance)  
**Est. Time:** 45 minutes  
**Complexity:** Medium

**What needs fixing:**

- Add time range filters to dashboard queries
- Limit queries to recent data (e.g., last 90 days)
- Add pagination to large result sets
- Prevent full table scans

**Implementation approach:**

```python
from django.utils import timezone
from datetime import timedelta
from django.core.paginator import Paginator

def dashboard_failed_audios(request):
    """
    Get failed audios with proper filtering and pagination.

    BEFORE: Scanned ALL failed audios (could be 1 million rows!)
    AFTER: Only last 90 days, paginated to 50 per page
    """
    # Filter to recent data
    cutoff_date = timezone.now() - timedelta(days=90)

    failed_audios = (
        Audio.objects.filter(
            status=AudioGenerationStatus.FAILED,
            created_at__gte=cutoff_date
        )
        .select_related('page', 'page__document', 'generated_by')
        .order_by('-created_at')
    )

    # Add pagination
    paginator = Paginator(failed_audios, per_page=50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'dashboard.html', {
        'failed_audios': page_obj,
        'total_count': paginator.count,
    })
```

**Where to add:**

- `speech_processing/dashboard_views.py` - all dashboard views
- Look for queries that fetch large result sets
- Add similar pattern to error_frequency, audio_stats, etc.

**Test cases:**

- Test with 100 records shows 50 per page
- Test pagination links work
- Test time filter excludes old data
- Verify query count stays constant regardless of total records

---

#### Issue #10: Input Validation for Integer Fields ⚠️ HIGH

**File:** `speech_processing/dashboard_views.py` (line ~308)  
**Severity:** 🟠 HIGH (Security)  
**Est. Time:** 10 minutes  
**Complexity:** Low

**What needs fixing:**

- Add bounds checking for `days` parameter
- Prevent negative numbers, zero, or extreme values
- Validate before using in queries

**Implementation approach:**

```python
def validate_days_parameter(days_str: str, min_days: int = 1, max_days: int = 365) -> int:
    """
    Validate and sanitize days parameter.

    Args:
        days_str: String value from request parameter
        min_days: Minimum allowed (default: 1)
        max_days: Maximum allowed (default: 365)

    Returns:
        Valid integer in range

    Raises:
        ValueError: If invalid input
    """
    try:
        days = int(days_str)
    except (ValueError, TypeError):
        return 30  # Default to 30 days

    # Enforce bounds
    if days < min_days or days > max_days:
        # Return default instead of error
        return 30

    return days

# Usage in view
days = validate_days_parameter(request.GET.get('days', 30))
start_date = timezone.now() - timedelta(days=days)
```

**Where to add:**

- `speech_processing/dashboard_views.py` - search for `int(days)` calls
- Could create `speech_processing/validators.py` utility module

**Test cases:**

- Test valid input (1-365) is accepted
- Test invalid input (not number) defaults to 30
- Test negative numbers default to 30
- Test 0 defaults to 30
- Test >365 defaults to 30

---

### 🟡 MEDIUM PRIORITY REMAINING (6)

#### Issue #14: Error Message Localization

**File:** All view files  
**Severity:** 🟡 MEDIUM (UX)  
**Est. Time:** 60 minutes

**What needs fixing:**

- Wrap error messages with Django's `gettext()` function
- Make error messages translatable
- Add translation files for multiple languages

---

#### Issue #16: Admin Audit Logging

**File:** `speech_processing/dashboard_views.py`  
**Severity:** 🟡 MEDIUM (Compliance)  
**Est. Time:** 40 minutes

**What needs fixing:**

- Log all admin settings changes
- Record user, timestamp, old value, new value
- Create audit trail for compliance

---

#### Issue #17: CSRF in AJAX

**File:** Template files and JavaScript  
**Severity:** 🟡 MEDIUM (Security)  
**Est. Time:** 20 minutes

**What needs fixing:**

- Verify all AJAX POST/PUT/DELETE include CSRF token
- Add CSRF token to headers in JavaScript

---

#### Issue #18: Task Failure Notifications

**File:** `document_processing/tasks.py`  
**Severity:** 🟡 MEDIUM (UX)  
**Est. Time:** 30 minutes

**What needs fixing:**

- Send email when tasks fail
- Notify admins of system errors
- Log failures for monitoring

---

#### Issue #19: Remove Sensitive Data from Logs

**File:** All files with logging  
**Severity:** 🟡 MEDIUM (Security)  
**Est. Time:** 20 minutes

**What needs fixing:**

- Don't log user emails, API keys, passwords
- Use masking functions for sensitive data
- Review all `logger.*()` calls

---

### 🔵 LOW PRIORITY REMAINING (4)

#### Issue #20: Type Hints and Docstrings

**File:** Multiple service files  
**Severity:** 🔵 LOW (Quality)  
**Est. Time:** 90 minutes

---

#### Issue #21: Refactor Permission Checks

**File:** `document_processing/views.py`  
**Severity:** 🔵 LOW (Quality)  
**Est. Time:** 30 minutes

---

#### Issue #22: Replace Magic Numbers

**File:** Multiple files  
**Severity:** 🔵 LOW (Quality)  
**Est. Time:** 20 minutes

---

#### Issue #23: Clean Unused Imports

**File:** Multiple files  
**Severity:** 🔵 LOW (Quality)  
**Est. Time:** 15 minutes

---

#### Issue #24: Health Check Endpoint

**File:** `core/urls.py`  
**Severity:** 🔵 LOW (DevOps)  
**Est. Time:** 20 minutes

---

## 📊 TIME ESTIMATES

| Priority  | Count  | Est. Time   | Per Issue      |
| --------- | ------ | ----------- | -------------- |
| Critical  | 2      | 50 min      | 25 min avg     |
| High      | 3      | 100 min     | 33 min avg     |
| Medium    | 6      | 220 min     | 37 min avg     |
| Low       | 4      | 175 min     | 44 min avg     |
| **TOTAL** | **15** | **545 min** | **36 min avg** |

**Total Remaining:** ~9 hours (1-2 business days)

---

## 🎯 RECOMMENDED NEXT SESSION PLAN

### Session 1: High-Value Quick Wins (2 hours)

1. **#10** - Input validation (10 min) ✅ QUICK
2. **#2** - SQL injection prevention (20 min) ✅ IMPORTANT
3. **#11** - Rate limiting (45 min) ✅ SECURITY
4. **#13** - Transaction safety (30 min) ✅ DATA SAFETY
5. **#9** - Query pagination (15 min) ✅ SETUP

### Session 2: Medium-Priority Features (3 hours)

1. **#14** - Localization setup
2. **#16** - Audit logging
3. **#17** - CSRF verification
4. **#18** - Failure notifications
5. **#19** - Log sanitization

### Session 3: Code Quality & Polish (2 hours)

1. **#20** - Type hints & docstrings
2. **#21** - Permission refactoring
3. **#22** - Magic numbers
4. **#23** - Cleanup imports
5. **#24** - Health check endpoint

---

## ✅ PRE-REQUISITES FOR NEXT SESSION

- [ ] Verify all 9 completed fixes deployed successfully
- [ ] Run test suite to ensure no regressions
- [ ] Performance test document list with 1000+ items
- [ ] Review any production logs for issues
- [ ] Get code review approval for completed fixes

---

**Status:** 🟡 **IN PROGRESS - GOOD MOMENTUM**

**Next Action:** Continue with Issue #2, #9, #10, #11, #13 in next session
