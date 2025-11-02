# Your Questions Answered: Document Sharing & Email Display

**Date:** November 1, 2025  
**Status:** ✅ Your system is properly configured!

---

## Quick Answer 1: What Happens When a User Shares a Document?

### The Flow

```
User A clicks "Share Document"
    ↓
Enters: user@example.com + Permission Level
    ↓
System creates/updates DocumentSharing record linking:
  • Document
  • Recipient User
  • Permission Level (VIEW_ONLY, COLLABORATOR, or CAN_SHARE)
  • Who shared it (User A)
    ↓
System logs the action in audit log (AudioAccessLog)
    ↓
**NO EMAIL SENT TO USER** (sharing happens silently in background)
    ↓
Recipient can now view/edit document based on permission level
```

### Permission Levels (What the Shared User Can Do)

| Permission       | View | Download | Generate Audio | Re-Share |
| ---------------- | ---- | -------- | -------------- | -------- |
| **VIEW_ONLY**    | ✓    | ✗        | ✗              | ✗        |
| **COLLABORATOR** | ✓    | ✓        | ✓              | ✗        |
| **CAN_SHARE**    | ✓    | ✓        | ✓              | ✓        |

### Behind the Scenes (Code)

**File:** `speech_processing/views.py` → `share_document()` function (lines 386-490)

```python
# Step 1: Verify permission
if document.user != request.user:
    # User doesn't own it, check if they have CAN_SHARE permission
    if not sharing.can_share():
        return error  # 403 Forbidden

# Step 2: Find recipient by email
user_to_share = User.objects.get(email=email)  # 404 if not found

# Step 3: Create or update DocumentSharing
sharing, created = DocumentSharing.objects.update_or_create(
    document=document,
    shared_with=user_to_share,
    defaults={
        "permission": permission,
        "shared_by": request.user
    }
)

# Step 4: Log the action
log_share_action(user=request.user, document=document, action=SHARE, ...)

# Step 5: Return success
return {"success": True, "created": created, "sharing_id": sharing.id}
```

### Database

```python
class DocumentSharing(models.Model):
    document = ForeignKey(Document)        # Which document
    shared_with = ForeignKey(User)         # Who it's shared with
    permission = CharField(choices=[...])  # Their permission
    shared_by = ForeignKey(User)          # Who shared it
    created_at = DateTimeField()          # When shared

    # Constraint: Can only have ONE sharing per document-user pair
    unique_together = ("document", "shared_with")
```

---

## Quick Answer 2: How to See Emails in the Terminal?

### Good News! ✅ You're Already Set Up!

Your development environment is **already configured** to display emails in the terminal!

**File:** `/core/settings/dev.py` (Line 30)

```python
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "webmaster@localhost"
```

### How It Works

When your Django app sends an email (like expiry warnings), instead of sending it over SMTP:

```
❌ Before: Email goes to SMTP server (you don't see it)
✅ After: Email prints to your terminal/console output
```

### Example: What You'll See

When an expiry warning email is sent, your terminal will show:

```
Content-Type: text/plain; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Subject: Audio Files Expiring Soon - Action Required
From: webmaster@localhost
To: alice@example.com
Date: Wed, 01 Nov 2025 14:23:45 -0000

Hi Alice,

Your audio file "Joanna" for document "Budget Planning" will expire in 25 days.

You can:
- Re-play the audio to reset the timer
- Download and save the audio
- Generate a new audio before expiry

Days until expiry: 25

Best regards,
TTS Project Team

---------- FORWARDED MESSAGE FOLLOWS ----------
Content-Type: text/html; charset="utf-8"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit

<html>
  <body>
    <h1>Audio Files Expiring Soon</h1>
    <p>Hi Alice,</p>
    <p>Your audio file <strong>Joanna</strong> for document
       <strong>Budget Planning</strong> will expire in <strong>25 days</strong>.</p>
    ...
  </body>
</html>
```

### Test It Yourself

Open a Django shell and send a test email:

```bash
# Open Django shell
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell
```

Then run:

```python
from django.core.mail import send_mail

send_mail(
    subject="Test Email from TTS Project",
    message="This is a test email to verify console backend is working.",
    from_email="webmaster@localhost",
    recipient_list=["test@example.com"],
    fail_silently=False,
)
```

**Expected result:** You'll see the email printed to the console!

### To Test the Real Task

```python
# In Django shell:
from speech_processing.tasks import check_expired_audios

result = check_expired_audios()
print(result)

# Watch the output - you'll see:
# 1. Task starting message
# 2. Any expiry warning emails as console output
# 3. Task completion message
```

---

## Full Workflow Example: From Sharing to Email

### Scenario

Alice shares a document with Bob. Bob generates audio. 6 months later, the audio is about to expire and a warning email is sent.

### Step-by-Step Timeline

**Day 1 - Document Creation**

```
Alice creates document "Budget Planning"
Document ID: 42
Owner: Alice
```

**Day 1 - Document Sharing**

```
1. Alice shares document 42 with bob@example.com
2. POST /speech/share/42/
3. Request body: {"email": "bob@example.com", "permission": "COLLABORATOR"}
4. DocumentSharing created:
   - document_id = 42
   - shared_with = Bob
   - permission = COLLABORATOR
   - shared_by = Alice
5. Audit log recorded: Alice shared document with Bob
6. Bob now has access! No email sent to Bob (silent sharing)
```

**Day 2 - Bob Generates Audio**

```
1. Bob generates audio in document 42
2. POST /speech/generate/123/
3. Audio created with:
   - document_id = 42
   - voice_id = "Joanna"
   - created_at = 2025-05-02
   - auto_delete_enabled = True (default)
   - expiry_days = 180
4. Audio status: GENERATED
5. S3 audio file uploaded
```

**Day 156 - Expiry Warning Check (daily task)**

```
check_expired_audios() task runs:

1. Find all audio records
2. For each audio:
   - created_at = 2025-05-02
   - Today = 2025-11-05 (156 days later)
   - Check if 155-175 days old?
   - YES! Audio is in warning window

3. Send expiry warning email:
   FROM: webmaster@localhost
   TO: bob@example.com
   SUBJECT: Audio Files Expiring Soon - Action Required

4. EMAIL CONTENT (displayed in console):

   Hi Bob,

   Your audio file "Joanna" for document "Budget Planning"
   will expire in 25 days.

   [Full email HTML printed to terminal]

5. Email console output shows in terminal!
```

**Day 180 - Expiry**

```
Audio expires:
- created_at = 2025-05-02
- Days passed = 180
- Audio marked as EXPIRED
- If auto_delete_enabled=True: S3 file deleted
- Audit log: Audio expired and deleted
```

---

## For Developers: How to Use These Features

### 1. Test Sharing

```bash
# Open Django shell
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

# Import needed models
from django.contrib.auth import get_user_model
from document_processing.models import Document
from speech_processing.models import DocumentSharing, SharingPermission

User = get_user_model()

# Get users and document
alice = User.objects.get(email="alice@example.com")
bob = User.objects.get(email="bob@example.com")
doc = Document.objects.first()  # Get first document

# Create sharing
sharing = DocumentSharing.objects.create(
    document=doc,
    shared_with=bob,
    permission=SharingPermission.COLLABORATOR,
    shared_by=alice
)

print(f"✅ Shared {doc.title} with {bob.email}")
print(f"   Permission: {sharing.permission}")
print(f"   Shared by: {sharing.shared_by.email}")

# Update permission
sharing.permission = SharingPermission.CAN_SHARE
sharing.save()
print(f"✅ Updated permission to: {sharing.permission}")

# Bob can now share with others!
print(f"✅ Bob can share: {sharing.can_share()}")
```

### 2. Test Email Display

```bash
# Open Django shell
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

# Send a test email
from django.core.mail import send_mail

recipients = ["alice@example.com", "bob@example.com"]
send_mail(
    subject="Test: Document Sharing Notification",
    message="You have been granted access to a document.",
    from_email="webmaster@localhost",
    recipient_list=recipients,
    fail_silently=False,
)

print("✅ Email sent! Check console for output")
```

### 3. Test Expiry Warning Task

```bash
# Open Django shell
docker-compose -f docker-compose.dev.yml run --rm web python manage.py shell

# Run the expiry check task
from speech_processing.tasks import check_expired_audios

print("Running expiry check...")
result = check_expired_audios()
print(f"\n✅ Task completed: {result['message']}")

# Watch console for email output!
```

### 4. Test API Endpoint Directly

```bash
# If running locally with curl
curl -X POST http://localhost:8000/speech/share/42/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "email": "bob@example.com",
    "permission": "COLLABORATOR"
  }'

# Expected response:
{
  "success": true,
  "message": "Document shared successfully with bob@example.com",
  "sharing_id": 42,
  "permission": "COLLABORATOR",
  "created": true
}
```

---

## Configuration Locations

| Feature                    | File                                  | Setting                                                            |
| -------------------------- | ------------------------------------- | ------------------------------------------------------------------ |
| **Email Console Output**   | `core/settings/dev.py`                | `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` |
| **Email Sender**           | `core/settings/dev.py`                | `DEFAULT_FROM_EMAIL = "webmaster@localhost"`                       |
| **Share Document View**    | `speech_processing/views.py:386`      | `def share_document(request, document_id)`                         |
| **DocumentSharing Model**  | `speech_processing/models.py:280`     | `class DocumentSharing(models.Model)`                              |
| **Permission Choices**     | `speech_processing/models.py:~270`    | `SharingPermission` enum                                           |
| **Expiry Warning Task**    | `speech_processing/tasks.py`          | `def check_expired_audios()`                                       |
| **Expiry Email Templates** | `templates/speech_processing/emails/` | `expiry_warning.html`, `expiry_warning.txt`                        |

---

## Email Backend Options (If You Want Different Behavior)

Your `dev.py` currently uses **Console Backend**. Here are alternatives:

### 1. Console Backend (Current) ✅

```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

**Emails print to console/terminal**  
Best for: Seeing emails while testing locally

### 2. File Backend

```python
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = '/tmp/app-messages'
```

**Emails saved to files on disk**  
Best for: Archiving emails, reviewing later

### 3. In-Memory Backend

```python
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

**Emails stored in RAM (Django test framework)**  
Best for: Automated tests

### 4. Real SMTP Backend (Production)

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
```

**Real emails sent via SMTP**  
Best for: Production deployment

---

## Summary

✅ **Question 1 - Document Sharing:**

- Creates `DocumentSharing` record linking document to user
- Assigns one of 3 permission levels (VIEW_ONLY, COLLABORATOR, CAN_SHARE)
- Logs sharing action in audit trail
- **NO email** sent to shared user (silent)

✅ **Question 2 - Email in Terminal:**

- Your system is **already configured**!
- `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` in `dev.py`
- Emails print directly to terminal
- Test it by running `check_expired_audios()` task or sending test email

🎯 **You're All Set!** Start testing with the examples above.

---

**For Complete Details:** See `DOCUMENT_SHARING_AND_EMAIL_GUIDE.md` in the project root
