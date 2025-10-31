# Speech Processing Tests - Investigation Report

**Date:** October 31, 2025  
**Scope:** speech_processing app test suite analysis  
**Test Results Summary:**

- **Total Tests:** 76 tests
- **Passing:** 50 tests ✅ (66%)
- **Failing:** 7 test failures ❌
- **Errors:** 19 test errors 🔴

---

## Executive Summary

The speech_processing test suite is testing critical audio generation, management, and sharing functionality but has significant issues with:

1. **Mock Path Errors (19 errors)** - Tests trying to mock non-existent methods in AudioGenerationService
2. **Permission/Status Errors (7 failures)** - Tests expecting 200 but getting 403, or assertion logic errors
3. **Function Signature Mismatches** - Celery tasks called with wrong number of arguments

**Status:** Major work needed to align tests with actual implementation. Most issues are related to service method availability and permission checks.

---

## Test Categories Overview

### ✅ Working Well (50 tests passing)

**Areas with full passing tests:**

- Audio Model Tests (Expiry, Quota, Soft Delete, Voice Uniqueness) - All passing ✅
- Sharing Model Tests (DocumentSharing, SiteSettings) - All passing ✅
- Sharing API Tests - Some issues but model layer works
- Models and Schema validation

### ❌ Problem Areas (26 tests with issues)

1. **Audio Generation Tasks** - 3 errors
2. **Export Audit Logs Tasks** - 3 errors
3. **Generate Audio API Endpoints** - 5 failures
4. **Delete/Sharing API Endpoints** - Multiple errors
5. **Check Expired Audios Tasks** - 1 failure + errors

---

## Detailed Issue Analysis

### CATEGORY 1: Mock Path Errors (19 ERRORS)

#### Issue 1.1: Wrong Mock Path - Not PollyService.generate_audio

**Affected Tests:** 3 tests
**Error Type:** AttributeError
**Severity:** HIGH

**Tests Affected:**

- `test_generate_audio_task_success`
- `test_generate_audio_task_failure`
- `test_generate_audio_task_retry_on_transient_error`

**Error Message:**

```
AttributeError: <class 'speech_processing.services.AudioGenerationService'>
does not have the attribute 'generate_audio'
```

**Root Cause:**
Tests are mocking `AudioGenerationService.generate_audio` but:

1. AudioGenerationService HAS `generate_audio_for_page()` method (NOT `generate_audio`)
2. The actual code calls `PollyService.generate_audio()` to do the heavy lifting

**Actual Code Flow:**

```python
# In generate_audio_task():
service = AudioGenerationService()
# This calls PollyService internally:
result = service.generate_audio_for_page(page, voice_id)  # NOT .generate_audio()
```

**Problem Location:** `speech_processing/tests/test_tasks.py` (line 49)

```python
# CURRENT (WRONG)
@patch("speech_processing.services.AudioGenerationService.generate_audio")  # ← Wrong method name!
def test_generate_audio_task_success(self, mock_generate):
```

**Solution:**

Change mock path from `AudioGenerationService.generate_audio` to `speech_processing.services.PollyService.generate_audio`:

```python
# FIXED
@patch("speech_processing.services.PollyService.generate_audio")
def test_generate_audio_task_success(self, mock_generate):
    mock_generate.return_value = {
        "s3_key": "audios/test-audio-123.mp3",
        "duration": Decimal("15.5"),
        "file_size": 250000,
    }
```

**Why This Works:**

- The task calls `AudioGenerationService.generate_audio_for_page()`
- That method internally creates and calls `PollyService.generate_audio()`
- Mocking PollyService.generate_audio prevents the actual AWS Polly call

---

#### Issue 1.2: S3 Deletion Happens Inline, Not in Dedicated Method

**Affected Tests:** 1 test
**Error Type:** AttributeError  
**Severity:** HIGH

**Test Affected:**

- `test_check_expired_audios_cleans_up_s3`

**Error Message:**

```
AttributeError: <class 'speech_processing.services.AudioGenerationService'>
does not have the attribute 'delete_from_s3'
```

**Root Cause:**
Test is mocking a non-existent `delete_from_s3` method. S3 deletion is NOT in a dedicated method - it happens inline in the `check_expired_audios` Celery task using the AWS S3 client directly.

**Actual Code Flow:**

```python
# In check_expired_audios task:
s3_client = boto3.client("s3")
s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
# NO separate method is called!
```

**Solution:**

Mock the boto3 S3 client instead of a non-existent method:

```python
# CURRENT (WRONG)
@patch("speech_processing.services.AudioGenerationService.delete_from_s3")
def test_check_expired_audios_cleans_up_s3(self, mock_delete):

# FIXED
@patch("boto3.client")
def test_check_expired_audios_cleans_up_s3(self, mock_boto_client):
    mock_s3_client = MagicMock()
    mock_boto_client.return_value = mock_s3_client

    # ... test code ...

    # Verify S3 delete_object was called
    mock_s3_client.delete_object.assert_called()
```

**Alternative Solution:**
Add a proper `delete_from_s3()` method to AudioGenerationService and refactor `check_expired_audios` to call it (cleaner design).

---

#### Issue 1.3: Sharing API Tests Using Wrong App Namespace in reverse()

**Affected Tests:** 12 sharing API tests
**Error Type:** NoReverseMatch / 404 errors
**Severity:** HIGH

**Tests Affected:**

- `test_list_shares_by_owner`
- `test_share_document_by_non_owner`
- `test_share_document_by_owner_success`
- `test_share_document_duplicate_share`
- `test_share_document_invalid_email`
- `test_share_document_with_can_share_permission`
- `test_list_shared_with_me`
- `test_unshare_by_non_owner`
- `test_unshare_by_owner_success`
- `test_update_permission_by_non_owner`
- `test_update_permission_by_owner`
- `test_update_permission_invalid_value`

**Root Cause:**
Tests are calling `reverse()` with the wrong app namespace. They're trying to look up endpoints in the `document_processing` app when the sharing endpoints are actually in the `speech_processing` app.

**Actual Problem Location:** `speech_processing/tests/test_sharing_api.py`

```python
# CURRENT (WRONG)
url = reverse(
    "document_processing:share_document",  # ← WRONG app namespace!
    kwargs={"document_id": self.document.id},
)

# CORRECT endpoints are defined in speech_processing/urls.py:
# app_name = "speech_processing"
```

**Why This Fails:**

1. Sharing endpoints are in `speech_processing/urls.py` with `app_name = "speech_processing"`
2. Tests are looking for endpoints in app namespace `"document_processing:share_document"`
3. Django reverse() can't find `document_processing:share_document` → NoReverseMatch error
4. Tests fail before even running the view logic

**Solution:**

Change all reverse() calls to use the correct app namespace:

```python
# FIXED
url = reverse(
    "speech_processing:share_document",  # ← CORRECT app namespace!
    kwargs={"document_id": self.document.id},
)
```

**Endpoints to Fix in Tests:**

All sharing-related reverse() calls must use `"speech_processing"` namespace:

- `speech_processing:share_document`
- `speech_processing:unshare_document`
- `speech_processing:document_shares`
- `speech_processing:shared_with_me`
- `speech_processing:update_share_permission`

**Quick Fix Script:**

In `speech_processing/tests/test_sharing_api.py`, replace all:

```python
"document_processing:
```

with:

```python
"speech_processing:
```

---

### CATEGORY 2: Permission and Status Errors (7 FAILURES)

#### Issue 2.1: Tests Expecting 200 But Views Return 403 for Permission Denied

**Affected Tests:** 5 tests
**Error Type:** AssertionError (403 != 200)
**Severity:** MEDIUM

**Tests Affected:**

1. `test_generate_audio_unauthorized_user` - Expected 200, got 403
2. `test_generate_audio_quota_exceeded` - Expected 200, got 403
3. `test_generate_audio_duplicate_voice` - Expected 200, got 403
4. `test_generate_audio_generation_disabled` - Expected 200, got 403
5. `test_delete_audio_by_non_owner` - Expected 200, got 403

**Root Cause:**
These tests check for error responses, but they expect HTTP 200 with JSON error body. The actual views return HTTP 403 (Forbidden) for permission errors, which is more RESTful.

**Actual View Code:**

```python
def generate_audio(request, page_id):
    # ... validation code ...
    allowed, error_msg = service.check_generation_allowed(
        request.user, page, voice_id
    )

    if not allowed:
        # View returns 403, not 200!
        return JsonResponse({"success": False, "error": error_msg}, status=403)
```

**Problem Location:** `speech_processing/tests/test_api_endpoints.py`

```python
# CURRENT (WRONG)
def test_generate_audio_unauthorized_user(self):
    # ... setup ...
    response = self.client.post(url, ...)
    self.assertEqual(response.status_code, 200)  # ← WRONG: Should be 403
    data = response.json()
    self.assertFalse(data["success"])
```

**Solution:**

Update test expectations to match actual HTTP status codes (403 for forbidden, not 200):

```python
# FIXED
def test_generate_audio_unauthorized_user(self):
    # ... setup ...
    response = self.client.post(url, ...)
    self.assertEqual(response.status_code, 403)  # ← CORRECT: Now expects 403
    data = response.json()
    self.assertFalse(data["success"])
    self.assertIn("permission", data["error"].lower())
```

**Why HTTP 403 is Better:**

- **RESTful Design**: HTTP 403 explicitly means "Forbidden"
- **Client Clarity**: Client receives proper HTTP error code, not guessing from JSON
- **Error Handling**: HTTP frameworks can handle 403 automatically
- **Caching**: Intermediaries know 403 shouldn't be cached

**All Tests to Fix:**

Update these 5 tests to expect `status_code=403` instead of `200`.

---

#### Issue 2.2: Tests Expecting 200 But Views Return 400 for Bad Request

**Affected Test:** 1 test
**Error Type:** AssertionError (400 != 200)
**Severity:** MEDIUM

**Test Affected:**

- `test_generate_audio_missing_voice_id`

**Root Cause:**
Test expects HTTP 200 with JSON error body, but the view returns HTTP 400 (Bad Request) for missing required parameters.

**Actual View Code:**

```python
def generate_audio(request, page_id):
    data = json.loads(request.body)
    voice_id = data.get("voice_id")

    if not voice_id:
        # Returns 400, not 200
        return JsonResponse(
            {"success": False, "error": "Voice ID is required"},
            status=400
        )
```

**Problem:**

```python
# CURRENT (WRONG)
def test_generate_audio_missing_voice_id(self):
    response = self.client.post(url, data=json.dumps({}), ...)
    self.assertEqual(response.status_code, 200)  # ← WRONG: Should be 400
```

**Solution:**

Update test to expect HTTP 400:

```python
# FIXED
def test_generate_audio_missing_voice_id(self):
    response = self.client.post(url, data=json.dumps({}), ...)
    self.assertEqual(response.status_code, 400)  # ← CORRECT: Now expects 400
    data = response.json()
    self.assertFalse(data["success"])
    self.assertIn("required", data["error"].lower())
```

**Why HTTP 400 is Correct:**

- **RESTful Design**: HTTP 400 means "Bad Request" (client sent invalid data)
- **Client Clarity**: Missing required fields = bad request from client
- **API Contract**: Clearly communicates validation failure to API consumers

---

#### Issue 2.3: check_expired_audios Task Doesn't Check auto_delete_enabled Setting

**Affected Test:** 1 test
**Error Type:** AssertionError
**Severity:** MEDIUM

**Test Affected:**

- `test_check_expired_audios_respects_settings`

**Error:**

```
AssertionError: 'EXPIRED' != AudioLifetimeStatus.ACTIVE
```

**Root Cause:**
The test expects that when `SiteSettings.auto_delete_expired_audios = False`, expired audios should NOT be marked as EXPIRED. However, the `check_expired_audios` task doesn't check this setting at all - it marks ALL expired audios as EXPIRED regardless of the setting.

**Actual Task Code (speech_processing/tasks.py):**

```python
@shared_task(bind=True)
def check_expired_audios(self):
    # NO CHECK for auto_delete_expired_audios setting!

    expired_audios = Audio.objects.filter(
        lifetime_status=AudioLifetimeStatus.ACTIVE,
        expires_at__lt=timezone.now()
    )

    for audio in expired_audios:
        # Deletes regardless of setting
        audio.lifetime_status = AudioLifetimeStatus.EXPIRED
        audio.save()

        s3_client = boto3.client("s3")
        s3_client.delete_object(Bucket=..., Key=audio.s3_key)
```

**What the Test Expects:**

```python
def test_check_expired_audios_respects_settings(self):
    # Disable auto-delete
    settings.auto_delete_expired_audios = False

    # ... create expired audio ...

    check_expired_audios()

    # Expects audio to still be ACTIVE
    audio.refresh_from_db()
    self.assertEqual(audio.lifetime_status, AudioLifetimeStatus.ACTIVE)
    # But it's EXPIRED instead!
```

**Solution:**

Add a settings check at the beginning of `check_expired_audios`:

```python
@shared_task(bind=True)
def check_expired_audios(self):
    settings = SiteSettings.get_settings()

    # Only process if enabled
    if not settings.auto_delete_expired_audios:
        return  # Exit early if auto-delete is disabled

    # ... rest of the deletion logic ...
    expired_audios = Audio.objects.filter(
        lifetime_status=AudioLifetimeStatus.ACTIVE,
        expires_at__lt=timezone.now()
    )

    for audio in expired_audios:
        audio.lifetime_status = AudioLifetimeStatus.EXPIRED
        audio.save()

        s3_client = boto3.client("s3")
        s3_client.delete_object(Bucket=..., Key=audio.s3_key)
```

**Alternative Design:**

You might also want to:

1. Keep marking as EXPIRED (for tracking)
2. Only delete from S3 if setting is enabled
3. Let expired audios persist if user wants to keep them

Then the check would look like:

```python
@shared_task(bind=True)
def check_expired_audios(self):
    settings = SiteSettings.get_settings()

    expired_audios = Audio.objects.filter(
        lifetime_status=AudioLifetimeStatus.ACTIVE,
        expires_at__lt=timezone.now()
    )

    for audio in expired_audios:
        audio.lifetime_status = AudioLifetimeStatus.EXPIRED
        audio.save()

        # Only delete from S3 if setting enables it
        if settings.auto_delete_expired_audios:
            s3_client = boto3.client("s3")
            s3_client.delete_object(Bucket=..., Key=audio.s3_key)
```

**Recommendation:** Option 2 - Mark as EXPIRED but only delete S3 if setting is enabled (allows recovery if user changes setting)

---

### CATEGORY 3: Function Signature Mismatches (3 ERRORS)

#### Issue 3.1: export_audit_logs_to_s3 Takes 0 Arguments But Called With 3

**Affected Tests:** 3 tests
**Error Type:** TypeError
**Severity:** HIGH

**Tests Affected:**

- `test_export_audit_logs_success`
- `test_export_audit_logs_filters_by_user`
- `test_export_audit_logs_filters_by_date_range`

**Error Message:**

```
TypeError: export_audit_logs_to_s3() takes 0 positional arguments but 3 were given
```

**Problem Location:** `speech_processing/tests/test_tasks.py` (line 160)

```python
def test_export_audit_logs_success(self):
    # ...
    export_audit_logs_to_s3(
        start_date=start_date,  # ← Called with arguments
        end_date=end_date,
        user_id=self.user.id,
    )
```

**Root Cause:**
The task is defined without parameters or with different parameters than what tests are calling it with.

**Problem in tasks.py:**

```python
# Current (Wrong)
@app.task
def export_audit_logs_to_s3():
    # No parameters!
    ...

# Should be
@app.task
def export_audit_logs_to_s3(start_date=None, end_date=None, user_id=None):
    # ...
```

**Solution:**
Update the task signature in `speech_processing/tasks.py` to accept the parameters the tests are passing:

```python
@app.task(bind=True)
def export_audit_logs_to_s3(self, start_date=None, end_date=None, user_id=None):
    # Implement filtering logic using these parameters
    logs = AudioAccessLog.objects.all()

    if start_date:
        logs = logs.filter(timestamp__gte=start_date)
    if end_date:
        logs = logs.filter(timestamp__lte=end_date)
    if user_id:
        logs = logs.filter(user_id=user_id)

    # ... export to S3
```

---

## Summary Table

| #   | Issue                                                                                          | Category      | Tests | Type  | Severity | Status |
| --- | ---------------------------------------------------------------------------------------------- | ------------- | ----- | ----- | -------- | ------ |
| 1.1 | Wrong mock path: AudioGenerationService.generate_audio instead of PollyService.generate_audio  | Mock Path     | 3     | ERROR | HIGH     | ⏳ Fix |
| 1.2 | delete_from_s3 doesn't exist - deletion is inline in task using boto3                          | Mock Path     | 1     | ERROR | HIGH     | ⏳ Fix |
| 1.3 | Sharing API tests using wrong app namespace (document_processing instead of speech_processing) | URL Namespace | 12    | ERROR | HIGH     | ⏳ Fix |
| 2.1 | Tests expect 200 but views correctly return 403 for permission denied                          | Status Code   | 5     | FAIL  | MEDIUM   | ⏳ Fix |
| 2.2 | Tests expect 200 but views correctly return 400 for bad request                                | Status Code   | 1     | FAIL  | MEDIUM   | ⏳ Fix |
| 2.3 | check_expired_audios doesn't check auto_delete_enabled before deletion                         | Logic         | 1     | FAIL  | MEDIUM   | ⏳ Fix |
| 3.1 | export_audit_logs_to_s3 signature takes 0 args but tests pass 3                                | Function Sig  | 3     | ERROR | HIGH     | ⏳ Fix |

---

## What's Working Well ✅

### Models (All Passing)

- Audio model expiry calculations
- Audio model quota enforcement
- Audio model soft delete
- Voice uniqueness constraints
- Document sharing permissions
- Site settings management

### Sharing Layer (All Passing)

- Document sharing model
- Permission levels (VIEW_ONLY, COLLABORATOR, CAN_SHARE)
- Unique together constraints

### Forms & Validation

- Audio creation validation
- Voice selection validation
- Permission validation

---

## What Needs Fixing ❌

### High Priority (19 Errors)

1. **AudioGenerationService mock paths** - Methods don't exist or named differently
2. **Sharing API endpoints** - Need investigation into specific failures
3. **Task function signatures** - Parameters not matching function definition

### Medium Priority (7 Failures)

1. **HTTP status codes** - Tests expect 200 but should expect 403/400
2. **Expired audio settings** - Task not respecting auto_delete_enabled flag
3. **Authorization checks** - Permission validation returning wrong status

---

## Recommended Fix Implementation Order

### Phase 1: Fix Mock Paths (HIGH PRIORITY - 16 errors)

**These fixes will reduce errors from 19 → 3:**

1. **Issue 1.1** - Change mock paths from `AudioGenerationService.generate_audio` to `speech_processing.services.PollyService.generate_audio` (3 tests)

   - Files: `speech_processing/tests/test_tasks.py`
   - Affected tests: test_generate_audio_task_success, test_generate_audio_task_failure, test_generate_audio_task_retry_on_transient_error

2. **Issue 1.2** - Change mock path from `AudioGenerationService.delete_from_s3` to `boto3.client` (1 test)

   - Files: `speech_processing/tests/test_tasks.py`
   - Affected test: test_check_expired_audios_cleans_up_s3

3. **Issue 1.3** - Fix URL namespace in sharing API tests from `document_processing:` to `speech_processing:` (12 tests)
   - Files: `speech_processing/tests/test_sharing_api.py`
   - Affected tests: All sharing API endpoint tests
   - Quick fix: `sed -i 's/"document_processing:/"speech_processing:/g' test_sharing_api.py`

### Phase 2: Fix HTTP Status Codes (MEDIUM PRIORITY - 6 failures)

**These fixes will reduce failures from 7 → 1:**

1. **Issue 2.1** - Update tests to expect 403 instead of 200 (5 tests)

   - Files: `speech_processing/tests/test_api_endpoints.py`
   - Change: `self.assertEqual(response.status_code, 200)` → `self.assertEqual(response.status_code, 403)`
   - Affected tests: test_generate_audio_unauthorized_user, test_generate_audio_quota_exceeded, test_generate_audio_duplicate_voice, test_generate_audio_generation_disabled, test_delete_audio_by_non_owner

2. **Issue 2.2** - Update test to expect 400 instead of 200 (1 test)
   - Files: `speech_processing/tests/test_api_endpoints.py`
   - Change: `self.assertEqual(response.status_code, 200)` → `self.assertEqual(response.status_code, 400)`
   - Affected test: test_generate_audio_missing_voice_id

### Phase 3: Fix Function Signatures (HIGH PRIORITY - 3 errors)

**These fixes will reduce errors from 3 → 0:**

1. **Issue 3.1** - Update `export_audit_logs_to_s3` task signature to accept parameters (3 tests)
   - Files: `speech_processing/tasks.py` and `speech_processing/tests/test_tasks.py`
   - Change function signature from `def export_audit_logs_to_s3():` to `def export_audit_logs_to_s3(self, start_date=None, end_date=None, user_id=None):`
   - Implement filtering logic based on parameters
   - Affected tests: test_export_audit_logs_success, test_export_audit_logs_filters_by_user, test_export_audit_logs_filters_by_date_range

### Phase 4: Fix Business Logic (MEDIUM PRIORITY - 1 failure)

**This fix will reduce failures from 1 → 0:**

1. **Issue 2.3** - Add settings check to `check_expired_audios` task (1 test)
   - Files: `speech_processing/tasks.py`
   - Add settings check at beginning of task or for S3 deletion
   - See solution in Issue 2.3 above
   - Affected test: test_check_expired_audios_respects_settings

---

## Test Failure Root Causes (Verified)

✅ **VERIFIED FINDINGS:**

1. ✅ **Issue 1.1 - CONFIRMED**: Mock path is wrong - should mock PollyService.generate_audio, not AudioGenerationService.generate_audio
2. ✅ **Issue 1.2 - CONFIRMED**: delete_from_s3 method doesn't exist - S3 deletion happens inline via boto3
3. ✅ **Issue 1.3 - CONFIRMED**: Sharing tests use wrong app namespace - should be speech_processing, not document_processing
4. ✅ **Issue 2.1 - CONFIRMED**: Views return 403 for permission denied - tests should expect 403, not 200
5. ✅ **Issue 2.2 - CONFIRMED**: Views return 400 for bad request - tests should expect 400, not 200
6. ✅ **Issue 2.3 - CONFIRMED**: check_expired_audios doesn't check auto_delete_enabled setting - needs check added
7. ✅ **Issue 3.1 - CONFIRMED**: export_audit_logs_to_s3 takes no parameters but tests pass 3 - signature needs update
