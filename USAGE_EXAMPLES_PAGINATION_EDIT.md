# Usage Examples: Pagination & Page Editing

**Date:** November 2, 2025

---

## Table of Contents

1. [User Stories](#user-stories)
2. [API Examples](#api-examples)
3. [Frontend Examples](#frontend-examples)
4. [Error Scenarios](#error-scenarios)
5. [Developer Examples](#developer-examples)

---

## User Stories

### Story 1: Alice Navigates a Multi-Page Document

**Scenario:** Alice has uploaded a 25-page document and wants to read through it.

**Steps:**

1. Alice logs in and goes to her documents list
2. She opens a document titled "Project Report"
3. She sees **Page 1 of 25** with the pagination buttons:
   ```
   [◀ Previous (disabled)]  Page 1 of 25  [Next ▶]
   ```
4. She reads the first page, then clicks **"Next Page"**
5. Page updates to show Page 2 with new content:
   ```
   [◀ Previous]  Page 2 of 25  [Next ▶]
   ```
6. She continues navigating through pages
7. When she reaches the last page:
   ```
   [◀ Previous]  Page 25 of 25  [Next (disabled)]
   ```

**Result:** ✅ Alice can easily navigate through all 25 pages

---

### Story 2: Bob Edits a Page He Wrote

**Scenario:** Bob is the owner of a document and wants to fix a typo on page 3.

**Steps:**

1. Bob opens his document to page 3
2. He notices a typo in the first paragraph
3. He clicks the **"Edit"** button in the content header
4. An edit modal opens showing the current markdown:

   ```markdown
   # Chapter 3: Analysis

   This chaptur contains important information...
   ```

5. In the live preview, he immediately sees it rendered:

   ```
   Chapter 3: Analysis

   This chaptur contains important information...
   ```

6. Bob clicks in the textarea and fixes the typo:

   ```markdown
   # Chapter 3: Analysis

   This chapter contains important information...
   ```

7. The preview updates instantly to show "chapter" correctly
8. Bob clicks **"Save Changes"** button
9. The modal closes and a toast notification appears:
   ```
   ✅ Page updated successfully!
   ```
10. The page now displays the corrected text

**Result:** ✅ Bob successfully fixed the typo

---

### Story 3: Charlie Tries to Edit a Shared Document

**Scenario:** Alice shared a document with Charlie (VIEW_ONLY permission). Charlie wants to edit it.

**Steps:**

1. Alice shares a document with Charlie (VIEW_ONLY permission)
2. Charlie logs in and opens the shared document
3. Charlie navigates to a page with an error
4. He looks for an "Edit" button but **doesn't see one**
5. He tries to manually navigate to `/documents/pages/42/edit/`
6. He gets a **403 Forbidden** error:
   ```json
   {
     "success": false,
     "error": "Permission denied"
   }
   ```
7. Charlie contacts Alice and asks her to fix the issue

**Result:** ✅ Charlie cannot edit (only owner can)

---

## API Examples

### API Example 1: Save Edited Page Content

**Request:**

```bash
curl -X POST http://localhost:8000/documents/pages/42/edit/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN_HERE" \
  -H "Cookie: csrftoken=YOUR_CSRF_TOKEN_HERE" \
  -d '{
    "markdown_content": "# Updated Title\n\nThis is the new content.\n\n## Section 1\n\nSome text here."
  }'
```

**Response (Success - 200 OK):**

```json
{
  "success": true,
  "message": "Page updated successfully",
  "page_id": 42,
  "html": "<h1>Updated Title</h1>\n<p>This is the new content.</p>\n<h2>Section 1</h2>\n<p>Some text here.</p>"
}
```

**Response (Error - Empty Content):**

```json
{
  "success": false,
  "error": "Content cannot be empty"
}
```

**Response (Error - Not Owner):**

```json
{
  "success": false,
  "error": "Permission denied"
}
```

---

### API Example 2: Render Markdown to HTML (Preview)

**Request:**

````bash
curl -X POST http://localhost:8000/documents/pages/render-markdown/ \
  -H "Content-Type: application/json" \
  -d '{
    "markdown": "# Heading\n\nThis is **bold** text.\n\n```python\nprint(\"hello\")\n```"
  }'
````

**Response (Success - 200 OK):**

```json
{
  "success": true,
  "html": "<h1>Heading</h1>\n<p>This is <strong>bold</strong> text.</p>\n<pre><code class=\"language-python\">print(\"hello\")\n</code></pre>"
}
```

**Response (Empty Markdown):**

```json
{
  "success": true,
  "html": "<p class='text-white-50'>Preview will appear here...</p>"
}
```

---

## Frontend Examples

### Example 1: JavaScript - Open Edit Modal

```javascript
// The edit button click handler
const editBtn = document.getElementById("editBtn");
editBtn.addEventListener("click", function () {
  const editModal = document.getElementById("editModal");
  const modal = new bootstrap.Modal(editModal);
  modal.show();
});
```

### Example 2: JavaScript - Live Preview Update

```javascript
// As user types in textarea, preview updates
const contentInput = document.getElementById("contentInput");
const previewContent = document.getElementById("previewContent");

contentInput.addEventListener("input", function () {
  const markdown = this.value;

  // Send to server for rendering
  fetch("/documents/pages/render-markdown/", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: JSON.stringify({ markdown: markdown }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        previewContent.innerHTML = data.html;
      }
    });
});
```

### Example 3: JavaScript - Save Changes

```javascript
// When user clicks Save button
const saveBtn = document.getElementById("saveBtn");
saveBtn.addEventListener("click", async function () {
  const content = document.getElementById("contentInput").value.trim();

  if (!content) {
    showToast("error", "Content cannot be empty");
    return;
  }

  // Show loading state
  this.disabled = true;
  this.textContent = "Saving...";

  try {
    const response = await fetch(`/documents/pages/${pageId}/edit/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({ markdown_content: content }),
    });

    const data = await response.json();

    if (data.success) {
      // Update page display
      document.getElementById("contentDisplay").innerHTML = data.html;

      // Close modal
      bootstrap.Modal.getInstance(editModal).hide();

      // Show success message
      showToast("success", "Page updated successfully!");
    } else {
      showToast("error", data.error);
    }
  } catch (error) {
    console.error("Error:", error);
    showToast("error", "Failed to save changes");
  } finally {
    this.disabled = false;
    this.textContent = "Save Changes";
  }
});
```

### Example 4: HTML - Pagination Section

```html
<!-- Bottom of page detail view -->
<nav aria-label="Page navigation" class="mt-4">
  <div class="d-flex justify-content-between align-items-center">
    <!-- Previous Button -->
    {% if previous_page_url %}
    <a href="{{ previous_page_url }}" class="btn btn-outline-primary">
      <i class="bi bi-chevron-left me-1"></i> Previous Page
    </a>
    {% else %}
    <button class="btn btn-outline-secondary" disabled>
      <i class="bi bi-chevron-left me-1"></i> Previous Page
    </button>
    {% endif %}

    <!-- Page Indicator -->
    <div class="text-center">
      <span class="text-white-50">
        Page <strong>{{ page.page_number }}</strong> of
        <strong>{{ total_pages }}</strong>
      </span>
    </div>

    <!-- Next Button -->
    {% if next_page_url %}
    <a href="{{ next_page_url }}" class="btn btn-outline-primary">
      Next Page <i class="bi bi-chevron-right ms-1"></i>
    </a>
    {% else %}
    <button class="btn btn-outline-secondary" disabled>
      Next Page <i class="bi bi-chevron-right ms-1"></i>
    </button>
    {% endif %}
  </div>
</nav>
```

---

## Error Scenarios

### Scenario 1: Empty Content Error

```javascript
// User clicks Save with empty textarea
POST /documents/pages/42/edit/
{
  "markdown_content": ""
}

Response:
{
  "success": false,
  "error": "Content cannot be empty"
}

Toast shown: "❌ Content cannot be empty"
Modal stays open for correction
```

### Scenario 2: Permission Denied Error

```javascript
// Non-owner tries to edit
POST /documents/pages/42/edit/
{
  "markdown_content": "# Hacked!"
}

Response (403):
{
  "success": false,
  "error": "Permission denied"
}

Toast shown: "❌ Permission denied"
Access denied to non-owner
```

### Scenario 3: Page Not Found Error

```javascript
// User navigates to non-existent page
GET /documents/docs/42/pages/999/

Response (404):
Django 404 page displayed
User sees "Page not found"
```

### Scenario 4: Network Error During Save

```javascript
// Network fails while saving
POST /documents/pages/42/edit/
[Network timeout after 30 seconds]

Result:
Toast shown: "❌ Failed to save changes"
Modal stays open
User can retry
```

---

## Developer Examples

### Example 1: Testing the Edit Endpoint

```bash
# 1. Create test data
docker-compose -f docker-compose.dev.yml exec web python manage.py shell

# In Python shell:
from django.contrib.auth import get_user_model
from document_processing.models import Document, DocumentPage

User = get_user_model()
user = User.objects.first()
doc = Document.objects.create(
    user=user,
    title="Test Document",
    status="COMPLETED"
)
page = DocumentPage.objects.create(
    document=doc,
    page_number=1,
    markdown_content="# Original Content"
)
print(f"Created page {page.id}")
```

```bash
# 2. Get CSRF token from page
curl -c cookies.txt http://localhost:8000/documents/docs/1/pages/1/

# 3. Extract CSRF token
CSRF_TOKEN=$(grep csrftoken cookies.txt | awk '{print $7}')

# 4. Test the edit endpoint
curl -b cookies.txt \
  -X POST http://localhost:8000/documents/pages/1/edit/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{
    "markdown_content": "# Updated Content\n\nWith new text."
  }'

# Expected Response:
{
  "success": true,
  "message": "Page updated successfully",
  "page_id": 1,
  "html": "<h1>Updated Content</h1>..."
}
```

### Example 2: Testing Permission Check

```bash
# 1. Create two users
docker-compose -f docker-compose.dev.yml exec web python manage.py shell

from django.contrib.auth import get_user_model
User = get_user_model()

alice = User.objects.create_user(
    username='alice',
    email='alice@example.com',
    password='testpass'
)
bob = User.objects.create_user(
    username='bob',
    email='bob@example.com',
    password='testpass'
)

from document_processing.models import Document, DocumentPage
doc = Document.objects.create(
    user=alice,
    title="Alice's Document",
    status="COMPLETED"
)
page = DocumentPage.objects.create(
    document=doc,
    page_number=1,
    markdown_content="# Alice's Content"
)
```

```bash
# 2. Login as Bob and try to edit Alice's page
curl -c cookies.txt \
  -d "username=bob&password=testpass&csrfmiddlewaretoken=XXX" \
  http://localhost:8000/accounts/login/

# 3. Try to edit Alice's page (should fail)
curl -b cookies.txt \
  -X POST http://localhost:8000/documents/pages/1/edit/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: $CSRF_TOKEN" \
  -d '{"markdown_content": "# Bob's Edit"}'

# Expected Response (403):
{
  "success": false,
  "error": "Permission denied"
}
```

### Example 3: Testing Pagination Logic

```python
# In Django shell
from document_processing.models import Document, DocumentPage
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.first()

# Create a 5-page document
doc = Document.objects.create(
    user=user,
    title="Test Doc",
    status="COMPLETED"
)

for i in range(1, 6):
    DocumentPage.objects.create(
        document=doc,
        page_number=i,
        markdown_content=f"# Page {i}"
    )

# Simulate page_detail view logic
doc_id = doc.id
for page_num in range(1, 6):
    total_pages = doc.pages.count()

    prev_url = f"/documents/docs/{doc_id}/pages/{page_num - 1}/" if page_num > 1 else None
    next_url = f"/documents/docs/{doc_id}/pages/{page_num + 1}/" if page_num < total_pages else None

    print(f"Page {page_num}:")
    print(f"  Previous: {prev_url or 'NONE (disabled)'}")
    print(f"  Next: {next_url or 'NONE (disabled)'}")
    print()

# Output:
# Page 1:
#   Previous: NONE (disabled)
#   Next: /documents/docs/1/pages/2/
#
# Page 2:
#   Previous: /documents/docs/1/pages/1/
#   Next: /documents/docs/1/pages/3/
# ...
# Page 5:
#   Previous: /documents/docs/1/pages/4/
#   Next: NONE (disabled)
```

### Example 4: Testing Markdown Rendering

````python
# In Django shell
import markdown as md

test_markdown = """
# Heading 1

This is **bold** and *italic*.

## Heading 2

Here's a list:
- Item 1
- Item 2
  - Nested

```python
def hello():
    print("world")
````

| Column 1 | Column 2 |
| -------- | -------- |
| Value 1  | Value 2  |

"""

html = md.markdown(
test_markdown,
extensions=[
"fenced_code",
"codehilite",
"tables",
"toc",
],
output_format="html5",
)

print(html)

# Output: Properly formatted HTML with syntax highlighting

````

---

## Integration Testing Checklist

```bash
# 1. Start Docker
docker-compose -f docker-compose.dev.yml up

# 2. Create test document with multiple pages
docker-compose -f docker-compose.dev.yml exec web python manage.py shell

# 3. Test in browser
# - Navigate to page detail
# - Test pagination forward/backward
# - Test edit modal opening
# - Test live preview updating
# - Test save functionality
# - Test error handling

# 4. Verify database changes persisted
# - Refresh page
# - Verify content still updated

# 5. Test permissions
# - Login as different user
# - Verify cannot edit
# - Verify can still view

# 6. Check logs
docker-compose -f docker-compose.dev.yml logs web | grep "Page.*updated"
````

---

**Created:** November 2, 2025  
**Last Updated:** November 2, 2025
