# Next Actions - Test Implementation & Fixes

**Date:** October 31, 2025  
**Current Status:** 8/13 task tests passing (62%), 7 issues identified  
**Priority Levels:** Critical → High → Medium → Low

---

## 🔴 CRITICAL - Must Fix Before Release

### 1. Debug Audio Expiry Logic (test_check_expired_audios_deletes_expired)

**Problem:**
- Test creates audio 210 days old, default retention 6 months (180 days)
- Expected: Audio should be marked as EXPIRED
- Actual: Audio remains ACTIVE
- Impact: Core functionality broken - old audios not being cleaned up

**Root Cause Analysis:**
```python
# In models.py - Audio.is_expired()
retention_days = settings_obj.audio_retention_months * 30  # Should be 180
if not self.last_played_at:
    return self.created_at < timezone.now() - timedelta(days=retention_days)
# For audio created 210 days ago: (now - 210) < (now - 180) = True ✓ Should work
```

**Investigation Steps:**
1. [ ] Add debug logging to `is_expired()` method
   ```python
   logger.info(f"Checking expiry: created={self.created_at}, now={timezone.now()}, retention={retention_days}")
   logger.info(f"Is expired: {result}")
   ```

2. [ ] Check SiteSettings.get_settings() in task
   - Verify `audio_retention_months` is correct
   - Add logging to confirm auto_delete_enabled is True

3. [ ] Verify timezone handling
   - Ensure created_at is set with timezone.now()
   - Check test database uses same timezone as task

4. [ ] Add assertions to test
   ```python
   print(f"Audio created_at: {expired_audio.created_at}")
   print(f"Current time: {timezone.now()}")
   print(f"Is expired: {expired_audio.is_expired()}")
   print(f"Auto delete enabled: {self.settings.auto_delete_expired_enabled}")
   ```

**Implementation:**
- [ ] File: `speech_processing/models.py` - Add logging to is_expired()
- [ ] File: `speech_processing/tasks.py` - Add logging to check_expired_audios()
- [ ] File: `speech_processing/tests/test_tasks.py` - Add debug assertions

**Success Criteria:**
- test_check_expired_audios_deletes_expired PASSES ✅
- Expired audio marked as EXPIRED
- Audio.lifetime_status = AudioLifetimeStatus.EXPIRED

---

### 2. Fix Warning Email Logic (test_check_expired_audios_sends_warning_emails)

**Problem:**
- Warning email should be sent when audio is within 30 days of expiry
- Test creates audio 155 days old (25 days from 180-day expiry)
- Expected: Warning email sent
- Actual: send_mail mock not called at all

**Root Cause Analysis:**
```python
# In tasks.py - check_expired_audios()
elif audio.needs_expiry_warning():  # This condition may not trigger
    # Send warning email
```

```python
# In models.py - needs_expiry_warning()
def needs_expiry_warning(self):
    days_left = self.days_until_expiry()
    return 0 < days_left <= 30  # Should be True for 25 days left
```

**Investigation Steps:**
1. [ ] Verify days_until_expiry() calculation
   ```python
   def days_until_expiry(self):
       retention_days = settings_obj.audio_retention_months * 30
       reference_date = self.last_played_at or self.created_at
       expiry_date = reference_date + timedelta(days=retention_days)
       days_left = (expiry_date - timezone.now()).days
       return max(0, days_left)
   ```

2. [ ] Add test assertions:
   ```python
   warning_audio.refresh_from_db()
   print(f"Days until expiry: {warning_audio.days_until_expiry()}")
   print(f"Needs warning: {warning_audio.needs_expiry_warning()}")
   ```

3. [ ] Check mock placement
   - Ensure `@patch("django.core.mail.send_mail")` decorator position
   - Verify it's patching the right send_mail import

4. [ ] Add logging to task:
   ```python
   logger.info(f"Checking warning for audio {audio.id}: days_left={audio.days_until_expiry()}, needs_warning={audio.needs_expiry_warning()}")
   ```

**Implementation:**
- [ ] File: `speech_processing/models.py` - Add logging to needs_expiry_warning()
- [ ] File: `speech_processing/tasks.py` - Add logging before elif check
- [ ] File: `speech_processing/tests/test_tasks.py` - Add debug assertions

**Success Criteria:**
- test_check_expired_audios_sends_warning_emails PASSES ✅
- Warning email sent when 0 < days_left <= 30
- mock_send_mail.called = True

---

### 3. Fix S3 Deletion Mock (test_check_expired_audios_cleans_up_s3)

**Problem:**
- S3 delete_object should be called for expired audios
- Test mocks boto3.client correctly
- Expected: mock_s3.delete_object.assert_called_once()
- Actual: delete_object called 0 times

**Root Cause Analysis:**
- Likely same root cause as #1 (is_expired() not returning True)
- OR boto3.client not being mocked properly in task

**Investigation Steps:**
1. [ ] Verify boto3.client is being called in task
   ```python
   # In check_expired_audios task
   s3_client = boto3.client("s3", ...)
   # This should use the mock when @patch("boto3.client")
   ```

2. [ ] Check mock setup in test
   ```python
   @patch("boto3.client")
   def test_check_expired_audios_cleans_up_s3(self, mock_boto_client):
       mock_s3 = MagicMock()
       mock_boto_client.return_value = mock_s3
       # This should work correctly
   ```

3. [ ] Add logging to verify flow:
   ```python
   logger.info(f"Attempting S3 delete for {audio.s3_key}")
   ```

**Implementation:**
- [ ] File: `speech_processing/tasks.py` - Verify boto3.client import and usage
- [ ] File: `speech_processing/tests/test_tasks.py` - Add debug logging
- [ ] May depend on fixing issue #1 (if not calling delete because is_expired() is False)

**Success Criteria:**
- test_check_expired_audios_cleans_up_s3 PASSES ✅
- S3 delete_object called with correct bucket and key
- mock_s3.delete_object.assert_called_once()

---

## 🟠 HIGH PRIORITY - Important but Not Blocking

### 4. Fix Retry Test (test_generate_audio_task_retry_on_transient_error)

**Problem:**
- Test should verify task retries on transient errors
- Current: Mock side_effect conflicts with task retry decorator
- Result: Task tries to retry, raising exception that breaks test

**Solution Options:**

**Option A: Mock the retry mechanism (Recommended)**
```python
@patch("speech_processing.services.PollyService.generate_audio")
@patch("speech_processing.tasks.generate_audio_task.request")
def test_generate_audio_task_retry_on_transient_error(self, mock_request, mock_generate):
    mock_generate.side_effect = Exception("Connection timeout")
    mock_request.retries = 3  # Already at max retries
    # Now task should not retry, just fail
    result = generate_audio_task(self.audio.id)
    assert result["success"] == False
```

**Option B: Refactor test to check retry logic separately**
```python
# Remove this test
# Add integration test that verifies retry with Celery worker
```

**Option C: Remove side_effect and test final state**
```python
@patch("speech_processing.services.PollyService.generate_audio")
def test_generate_audio_task_retry_on_transient_error(self, mock_generate):
    # Just test that on final failure, audio is marked FAILED
    mock_generate.side_effect = Exception("Connection timeout")
    # Don't test retry mechanism in unit test
```

**Recommendation:** Use Option A - Mock request.retries

**Implementation:**
- [ ] File: `speech_processing/tests/test_tasks.py` - Refactor test_generate_audio_task_retry_on_transient_error
- [ ] Add @patch for generate_audio_task.request
- [ ] Set mock_request.retries = 3 (max retries)
- [ ] Assert final result is failed

**Success Criteria:**
- test_generate_audio_task_retry_on_transient_error PASSES ✅
- No retry exception raised
- Audio status = FAILED

---

## 🟡 MEDIUM PRIORITY - Run Full Test Suite

### 5. Run All 76 Speech Processing Tests

**Purpose:**
- Verify all fixes work together
- Test API endpoint tests (403/400 status fixes)
- Test sharing API tests (namespace fixes)

**Tests to Verify:**
- [ ] 13 task tests → 13/13 passing (currently 8/13)
- [ ] 31 API endpoint tests (authorization & status code fixes)
- [ ] 12 sharing API tests (namespace fixes)
- [ ] 10 model tests (should still pass)
- [ ] 10 other tests (should still pass)

**Command to Run:**
```bash
docker-compose -f docker-compose.dev.yml run --rm web python manage.py test speech_processing -v 2
```

**Success Criteria:**
- 76/76 tests passing ✅
- 0 failures
- 0 errors

---

### 6. Run All Document Processing Tests

**Purpose:**
- Ensure no regressions from task fixes
- Verify sharing API changes don't break document tests

**Tests to Verify:**
- [ ] All document_processing tests should still pass (previously: 14/15)
- [ ] Test sharing endpoints still work

**Command to Run:**
```bash
docker-compose -f docker-compose.dev.yml run --rm web python manage.py test document_processing -v 2
```

**Success Criteria:**
- All document_processing tests passing
- 0 new failures

---

## 🟢 LOW PRIORITY - Long Term Improvements

### 7. Refactor Expiry Logic for Better Testability

**Current Problem:**
- Complex multi-condition checks hard to test
- SiteSettings.get_settings() called multiple times
- Timezone handling inconsistent

**Recommended Changes:**
```python
# In Audio model - Add helper method
def get_retention_days(self):
    """Get retention period from settings (testable)."""
    from speech_processing.models import SiteSettings
    settings_obj = SiteSettings.get_settings()
    return settings_obj.audio_retention_months * 30

def get_reference_date(self):
    """Get reference date for expiry calculation (testable)."""
    return self.last_played_at or self.created_at

def is_expired(self):
    """Check if audio should be expired."""
    retention_days = self.get_retention_days()
    reference_date = self.get_reference_date()
    return reference_date < timezone.now() - timedelta(days=retention_days)
```

**Implementation:**
- [ ] Refactor Audio model methods
- [ ] Add unit tests for new methods
- [ ] Update task to use new methods

---

### 8. Create Test Fixtures for Common Patterns

**Current Problem:**
- Repeated mock setup code
- Repeated test data creation
- Timezone handling errors

**Recommended Fixtures:**
```python
# In conftest.py or test_fixtures.py
@pytest.fixture
def expired_audio(user, document, page):
    """Create an audio that's definitely expired."""
    audio = Audio.objects.create(
        page=page,
        voice=TTSVoice.JOANNA,
        generated_by=user,
        s3_key="audios/expired.mp3",
        status=AudioGenerationStatus.COMPLETED,
        lifetime_status=AudioLifetimeStatus.ACTIVE,
    )
    audio.created_at = timezone.now() - timedelta(days=210)
    audio.save()
    return audio

@pytest.fixture
def warning_audio(user, document, page):
    """Create audio that needs expiry warning."""
    audio = Audio.objects.create(...)
    audio.created_at = timezone.now() - timedelta(days=155)
    audio.save()
    return audio
```

**Implementation:**
- [ ] Create `speech_processing/tests/conftest.py`
- [ ] Add common fixtures
- [ ] Update tests to use fixtures

---

### 9. Add Integration Tests

**Missing Test Coverage:**
- [ ] End-to-end expiry task (with DB, no mocks)
- [ ] Email notification system
- [ ] S3 cleanup workflow
- [ ] Celery task execution

**Implementation:**
```python
# speech_processing/tests/test_integration.py
class CheckExpiredAudiosIntegrationTest(TransactionTestCase):
    def test_expiry_task_e2e(self):
        # Create real audio, run task without mocks
        # Verify actual S3 calls would be made
        # Verify emails would be sent
```

---

## 📋 IMPLEMENTATION CHECKLIST

### This Week
- [ ] Fix issue #1: Audio expiry logic (CRITICAL)
- [ ] Fix issue #2: Warning email logic (CRITICAL)
- [ ] Fix issue #3: S3 deletion mock (CRITICAL)
- [ ] Fix issue #4: Retry test (HIGH)
- [ ] Run full speech_processing test suite (MEDIUM)
- [ ] Run document_processing test suite (MEDIUM)

### Next Week
- [ ] Refactor expiry logic (LOW)
- [ ] Create test fixtures (LOW)
- [ ] Add integration tests (LOW)
- [ ] Update documentation

---

## 📊 Success Metrics

### Test Coverage
| Suite | Current | Target | Status |
|-------|---------|--------|--------|
| Task Tests | 8/13 | 13/13 | 🔴 |
| API Tests | ? | 31/31 | ⏳ |
| Sharing Tests | ? | 12/12 | ⏳ |
| Model Tests | ? | 10/10 | ⏳ |
| Speech Processing | 8/76 | 76/76 | 🔴 |
| Document Processing | 14/15 | 15/15 | 🟡 |
| **TOTAL** | **~36/120** | **120/120** | **30%** |

### Code Quality
- [ ] All tests passing
- [ ] No mock-related warnings
- [ ] Consistent timezone handling
- [ ] Clear error messages in logs

### Documentation
- [ ] TEST_INVESTIGATION.md updated
- [ ] TEST_FIXES_SUMMARY.md updated
- [ ] NEXT_ACTIONS.md complete
- [ ] Code comments for complex logic

---

## 🔗 Related Files

### Key Files to Review/Modify
- `speech_processing/models.py` - Audio model, is_expired(), needs_expiry_warning()
- `speech_processing/tasks.py` - check_expired_audios(), export_audit_logs_to_s3()
- `speech_processing/tests/test_tasks.py` - All task tests
- `speech_processing/tests/test_api_endpoints.py` - API status code tests
- `speech_processing/tests/test_sharing_api.py` - Sharing endpoint tests

### Documentation
- `TEST_INVESTIGATION.md` - Original investigation findings
- `TEST_FIXES_SUMMARY.md` - Fixes applied
- `NEXT_ACTIONS.md` - This file

---

## 🎯 Final Goal

**Get all 76 speech_processing tests passing + keep document_processing at 15/15 passing**

This will complete the testing suite implementation and ensure the audio generation, expiry, and sharing features work correctly.

