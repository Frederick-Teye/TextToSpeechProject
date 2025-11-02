# Document Sharing & Email System Explanation

**Date:** November 1, 2025  
**Purpose:** Explain how document sharing works and how to view emails in the terminal

---

## Part 1: How Document Sharing Works

### Overview

When you share a document with another person, the system creates a **DocumentSharing** record that:

1. Links the document to another user
2. Specifies what permission level they have
3. Logs the sharing action for audit purposes

### The Process Step-by-Step

```
Owner clicks "Share Document"
         ↓
Owner enters recipient email + permission level
         ↓
System creates DocumentSharing record
         ↓
System logs the SHARE action in AudioAccessLog
         ↓
Shared user can now view/edit document based on permission level
```

### Code Implementation

**File:** `speech_processing/views.py:386-490`  
**Function:** `share_document(request, document_id)`

### Step-by-Step Code Flow

#### Step 1: Extract Request Data

```python
data = json.loads(request.body)
email = data.get("email")
permission = data.get("permission", "VIEW_ONLY")
```

**What happens:**

- Gets email address of person to share with
- Gets permission level (defaults to VIEW_ONLY if not specified)
- Permission options: `VIEW_ONLY`, `COLLABORATOR`, `CAN_SHARE`

#### Step 2: Verify Sharing Permission

```python
document = get_object_or_404(Document, id=document_id)

if document.user != request.user:
    # Check if user has CAN_SHARE permission
    sharing = DocumentSharing.objects.get(
        document=document, shared_with=request.user
    )
    if not sharing.can_share():
        return JsonResponse(
            {"success": False, "error": "You don't have permission to share"},
            status=403
        )
```

**What happens:**

- Only the document owner OR someone with `CAN_SHARE` permission can share
- If you don't own it and don't have CAN_SHARE permission, request is denied (403 Forbidden)

#### Step 3: Find the Recipient User

```python
try:
    user_to_share = User.objects.get(email=email)
except User.DoesNotExist:
    return JsonResponse(
        {"success": False, "error": f"User with email '{email}' not found"},
        status=404
    )
```

**What happens:**

- Looks up user by email in the database
- If not found, returns 404 error

#### Step 4: Validate Permission Level

```python
valid_permissions = [p.value for p in SharingPermission]
if permission not in valid_permissions:
    return JsonResponse(
        {"success": False, "error": f"Invalid permission"},
        status=400
    )
```

**What happens:**

- Ensures permission is one of: `VIEW_ONLY`, `COLLABORATOR`, or `CAN_SHARE`
- Rejects invalid permission values

#### Step 5: Create or Update Sharing Record

```python
sharing, created = DocumentSharing.objects.update_or_create(
    document=document,
    shared_with=user_to_share,
    defaults={"permission": permission, "shared_by": request.user}
)
```

**What happens:**

- Creates new sharing record OR updates existing one with new permission
- Records who shared it (the current user)
- `created` flag tells if this is new share or permission update

#### Step 6: Log the Action

```python
log_share_action(from speech_processing.tasks import check_expired_audios

result = check_expired_audios()
print(result)
    user=request.user,
    document=document,
    action=AudioAction.SHARE,
    ip_address=get_client_ip(request),
    user_agent=get_user_agent(request)
)
```

**What happens:**

- Records sharing action in audit log (AudioAccessLog)
- Captures user IP and browser info for security

#### Step 7: Return Success

```python
return JsonResponse({
    "success": True,
    "message": f"Document shared successfully with {email}",
    "sharing_id": sharing.id,
    "permission": sharing.permission,
    "created": created
})
```

**What happens:**

- Returns success response with sharing details
- Frontend can use `created` flag to show "Shared" vs "Permission Updated" message

### Permission Levels Explained

#### VIEW_ONLY (Default) 

- Can view document and audio files
- Cannot generate new audio
- Cannot download files
- Cannot share document with others
- Cannot edit document

```python
def can_generate_audio(self):
    return False  # VIEW_ONLY cannot generate

def can_share(self):
    return False  # VIEW_ONLY cannot share
```

#### COLLABORATOR

- Can view document and audio files
- Can generate new audio
- Can download files
- Cannot share document with others
- Cannot edit document title/content

```python
def can_generate_audio(self):
    return True  # COLLABORATOR can generate

def can_share(self):
    return False  # COLLABORATOR cannot share
```

#### CAN_SHARE

- Can view document and audio files
- Can generate new audio
- Can download files
- **Can share document with others** ← Highest permission
- Can edit permissions for already-shared users

```python
def can_generate_audio(self):
    return True  # CAN_SHARE can generate

def can_share(self):
    return True  # CAN_SHARE can share
```

### What Gets Logged

When sharing happens, an `AudioAccessLog` entry is created with:

```python
{
    "user": "owner@example.com",           # Who shared it
    "document": "Document 123",            # Which document
    "action": "SHARE",                     # Action type
    "timestamp": "2025-11-01 10:30:00",   # When shared
    "ip_address": "192.168.1.100",        # Sharer's IP
    "user_agent": "Mozilla/5.0..."        # Sharer's browser
}
```

### Database Schema

```pythonfrom speech_processing.tasks import check_expired_audios

result = check_expired_audios()
print(result)
class DocumentSharing(models.Model):
    document = ForeignKey(Document)           # The document being shared
    shared_with = ForeignKey(User)            # Who it's shared with
    permission = CharField(choices=[
        "VIEW_ONLY",
        "COLLABORATOR",
        "CAN_SHARE"
    ])                                        # Their permission level
    shared_by = ForeignKey(User)             # Who shared it
    created_at = DateTimeField()             # When it was shared

    unique_together = ("document", "shared_with")  # One share per user per doc
```

### Example: Complete Sharing Scenario

**Scenario:** Alice shares Document "Budget Planning" with Bob

```
1. Alice (owner) clicks "Share"
   ├─ Enters: email=bob@company.com
   └─ Selects: permission=COLLABORATOR

2. System looks up Bob in database
   ✓ Found: bob@company.com exists

3. System validates permission
   ✓ Valid: COLLABORATOR is allowed

4. System creates/updates sharing record
   ├─ document_id = 42
   ├─ shared_with_id = 5 (Bob)
   ├─ permission = "COLLABORATOR"
   └─ shared_by_id = 3 (Alice)

5. System logs the action
   ├─ AudioAccessLog created
   ├─ action = SHARE
   └─ timestamp = 2025-11-01 10:30:00

6. System returns success
   └─ {"success": true, "message": "Document shared with bob@company.com"}

7. Bob can now:
   ✓ View the document
   ✓ Generate new audio
   ✓ Download audio files
   ✗ Share with others (needs CAN_SHARE)
   ✗ Edit document title (read-only)
```

### Error Cases

**Error 1: User doesn't exist**

```python
Status: 404 Not Found
Response: {"success": false, "error": "User with email 'typo@example.com' not found"}
```

**Error 2: No permission to share**

```python
Status: 403 Forbidden
Response: {"success": false, "error": "You don't have permission to share this document"}
```

**Error 3: Invalid permission level**

```python
Status: 400 Bad Request
Response: {"success": false, "error": "Invalid permission. Must be one of: VIEW_ONLY, COLLABORATOR, CAN_SHARE"}
```

**Error 4: Trying to share with self**

```python
Status: 400 Bad Request
Response: {"success": false, "error": "Cannot share document with yourself"}
```

---

## Part 2: How to See Emails in the Terminal

### The Problem

Currently, when the expiry warning email would be sent:

```python
send_mail(
    subject="Audio Files Expiring Soon - Action Required",
    message=plain_message,
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=[user_email],
    html_message=html_message,
    fail_silently=False,
)
```

It tries to send a real email, which requires:

- SMTP server configured
- Email credentials
- Network access

This doesn't work well in development!

### Solution: Use Console Email Backend

Django provides a **Console Email Backend** that prints emails to the console instead of sending them. Perfect for development!

### How to Enable It

**File:** `core/settings/dev.py` (or create if it doesn't exist)

Add this code:

```python
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # For production
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # For development

# Optional: Configure email sender
DEFAULT_FROM_EMAIL = 'noreply@tts-project.local'
```

### What You'll See in Terminal

When the expiry warning task runs, instead of sending an email, you'll see:

```
[12/Nov/2025 14:23:45] "POST /api/check-expired-audios/" 200 OK
Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Audio Files Expiring Soon - Action Required
From: noreply@tts-project.local
To: alice@example.com

Hi Alice,

Your audio file "Joanna" for document "Budget Planning" will expire in 25 days.

You can:
- Re-play the audio to reset the timer
- Download and save the audio
- Generate a new audio before expiry

Days until expiry: 25

Best regards,
TTS Project Team

---------- MESSAGE FOLLOWS ----------
Content-Type: text/html; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <h1>Audio Files Expiring Soon</h1>
    <p>Hi Alice,</p>
    ...
  </body>
</html>
```

### Step-by-Step Setup

#### 1. Check Current Email Backend

```bash
cd /home/frederick/Documents/code/tts_project
cat core/settings/dev.py | grep EMAIL_BACKEND
```

Expected: Nothing (not set), or `smtp.EmailBackend`

#### 2. Add Console Backend

```bash
# Add to dev.py
echo "EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'" >> core/settings/dev.py
```

Or manually edit `core/settings/dev.py` and add:

```python
# Email configuration for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@tts-project.local'
```

#### 3. Verify It's Set

```bash
cat core/settings/dev.py | grep -A2 EMAIL_BACKEND
```

Expected:

```
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@tts-project.local'
```

#### 4. Restart Django

```bash
docker-compose -f docker-compose.dev.yml restart web
```

### Test It Works

Run the expiry check task manually:

```bash
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

# In the shell:
>>> from speech_processing.tasks import check_expired_audios
>>> result = check_expired_audios()
>>> print(result)
{'success': True, 'message': '...', ...}
```

**In the terminal you'll see:**

```
[INFO] Starting expired audios check task
Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Audio Files Expiring Soon - Action Required
From: noreply@tts-project.local
To: alice@example.com

Hi Alice,

Your audio file "Joanna" for document "Budget Planning" will expire in 25 days...
```

### Alternative: File Backend (Save Emails to Disk)

If you prefer to save emails to files instead of printing to console:

```python
# core/settings/dev.py

EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = '/tmp/app-messages'  # Or any directory
DEFAULT_FROM_EMAIL = 'noreply@tts-project.local'
```

**Result:** Emails saved to `/tmp/app-messages/` as .eml files

View them:

```bash
cat /tmp/app-messages/email-*.txt
```

### Alternative: In-Memory Backend (For Testing)

For automated tests, use the in-memory backend:

```python
# core/settings/test.py (or in test setup)

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

**Result:** Emails stored in memory (not sent), accessible via:

```python
from django.core.mail import outbox

# In your test:
result = check_expired_audios()
assert len(outbox) == 1
assert outbox[0].subject == "Audio Files Expiring Soon - Action Required"
assert "alice@example.com" in outbox[0].to
```

### Email Backends Comparison

| Backend     | Use Case    | Output            | Good For                    |
| ----------- | ----------- | ----------------- | --------------------------- |
| **Console** | Development | Print to terminal | See emails while developing |
| **File**    | Development | Save to disk      | Archive/review later        |
| **SMTP**    | Production  | Send real emails  | Real email delivery         |
| **Locmem**  | Testing     | Store in memory   | Automated tests             |

---

## Complete Example: Sharing + Email Notification

Here's how sharing and emails work together:

### Scenario: Alice Shares Document with Bob, Bob's Audio Expires

```
Timeline:
─────────

1. Alice shares document with Bob
   │
   ├─ POST /speech/share/42/
   ├─ Body: {"email": "bob@example.com", "permission": "COLLABORATOR"}
   │
   └─ Result:
       ├─ DocumentSharing record created
       ├─ AudioAccessLog: SHARE action logged
       └─ Response: {"success": true, "message": "Document shared with bob@example.com"}

2. Bob generates audio (as COLLABORATOR)
   │
   ├─ POST /speech/generate/123/
   ├─ Body: {"voice_id": "Joanna"}
   │
   └─ Result:
       ├─ Audio record created
       ├─ Audio status = PENDING
       └─ Async task started: generate_audio_task

3. Time passes (6 months)
   │
   └─ Audio created_at = 2025-05-01

4. Daily: check_expired_audios task runs
   │
   ├─ Finds audio created 2025-05-01
   ├─ Calculates: Today (2025-11-01) - 180 days = 2025-05-04
   ├─ Audio 2025-05-01 < 2025-05-04 = EXPIRED ✓
   │
   └─ Actions:
       ├─ Check needs_expiry_warning() (triggered earlier at day ~155)
       ├─ [If day 155] Send warning email
       ├─ [If day 180+] Mark as EXPIRED
       ├─ [If day 180+ AND auto_delete=true] Delete S3 file
       └─ Log all actions in AudioAccessLog

5. Email Console Output (if not yet expired)
   │
   └─ Terminal shows:
       ┌─────────────────────────────────────┐
       │ Content-Type: text/plain            │
       │ Subject: Audio Files Expiring Soon  │
       │ From: noreply@tts-project.local    │
       │ To: bob@example.com                │
       │                                     │
       │ Hi Bob,                            │
       │                                     │
       │ Your audio file "Joanna" for       │
       │ document "Budget Planning" will     │
       │ expire in 25 days...               │
       └─────────────────────────────────────┘
```

---

## Summary: Two Key Concepts

### 1. Document Sharing

- **Purpose:** Share documents with other users with specific permissions
- **Permission Levels:** VIEW_ONLY < COLLABORATOR < CAN_SHARE
- **Logged:** Every share action is recorded in audit log
- **Security:** Only owner or CAN_SHARE user can share

### 2. Email in Terminal

- **Problem:** Need to see emails during development
- **Solution:** Use Console Email Backend
- **Configuration:** Add `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` to settings
- **Result:** Emails print to terminal instead of being sent
- **Alternatives:** File, In-Memory, or SMTP backends available

---

## Quick Reference

### Sharing API Endpoint

```
POST /speech/share/<document_id>/
{
    "email": "user@example.com",
    "permission": "COLLABORATOR"  # or VIEW_ONLY, CAN_SHARE
}

Response 200: {"success": true, ...}
Response 403: Not authorized to share
Response 404: User not found
Response 400: Invalid permission
```

### Enable Console Email Backend

```python
# core/settings/dev.py
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### Test Sharing in Django Shell

```bash
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

>>> from django.contrib.auth import get_user_model
>>> from document_processing.models import Document
>>> from speech_processing.models import DocumentSharing, SharingPermission
>>> User = get_user_model()
>>> alice = User.objects.get(email="alice@example.com")
>>> bob = User.objects.get(email="bob@example.com")
>>> doc = Document.objects.get(id=1)
>>>
>>> # Create sharing
>>> sharing = DocumentSharing.objects.create(
...     document=doc,
...     shared_with=bob,
...     permission=SharingPermission.COLLABORATOR,
...     shared_by=alice
... )
>>> print(f"Shared with: {sharing.shared_with.email}, Permission: {sharing.permission}")
Shared with: bob@example.com, Permission: COLLABORATOR
```

### Test Email in Django Shell

```bash
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

>>> from django.core.mail import send_mail
>>>
>>> send_mail(
...     subject="Test Email",
...     message="This is a test",
...     from_email="noreply@tts-project.local",
...     recipient_list=["bob@example.com"],
...     fail_silently=False
... )
1  # Returns number of emails sent

# You'll see output in terminal:
# Content-Type: text/plain; charset="utf-8"
# Subject: Test Email
# From: noreply@tts-project.local
# To: bob@example.com
#
# This is a test
```

---

**For More Information:**

- See `FEATURES_IMPLEMENTED.md` for audio expiry email details
- See `speech_processing/views.py:386-490` for complete sharing implementation
- Django Docs: https://docs.djangoproject.com/en/5.2/topics/email/

**Created:** November 1, 2025
