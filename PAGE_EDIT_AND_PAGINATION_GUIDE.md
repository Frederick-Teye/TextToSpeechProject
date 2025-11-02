# Page Detail View: Pagination & Edit Features

**Date:** November 2, 2025  
**Feature:** Added pagination buttons and inline edit functionality to page detail view

---

## Overview

The page detail view now includes:

1. **Pagination Buttons** - Navigate between pages in a document
2. **Edit Modal** - Edit markdown content for each page (owner only)
3. **Live Preview** - Real-time markdown rendering while editing

---

## Features

### 1. Pagination Buttons

Located at the bottom of the page detail view.

```
[< Previous Page]  Page 3 of 25  [Next Page >]
```

**Behavior:**

- Previous button disabled on first page
- Next button disabled on last page
- Click to navigate between pages
- Page number indicator shows current position

**Files Modified:**

- `templates/document_processing/page_detail.html` - Added pagination section

---

### 2. Edit Page Content

An "Edit" button appears in the content card header (visible only to document owner).

```
┌─────────────────────────┬──────────┐
│ Content          │ Edit  │
└─────────────────────────┴──────────┘
```

**Click "Edit" to open the edit modal:**

```
┌──────────────────────────────────────────┐
│ Edit Page 3               [×]            │
├──────────────────────────────────────────┤
│                                          │
│ Markdown Content                         │
│ ┌──────────────────────────────────────┐ │
│ │ # Heading                            │ │
│ │ This is **bold** text                │ │
│ │ - List item 1                        │ │
│ │ - List item 2                        │ │
│ └──────────────────────────────────────┘ │
│                                          │
│ Preview                                  │
│ ┌──────────────────────────────────────┐ │
│ │ Heading                              │ │
│ │ This is bold text                    │ │
│ │ • List item 1                        │ │
│ │ • List item 2                        │ │
│ └──────────────────────────────────────┘ │
│                                          │
├──────────────────────────────────────────┤
│ [Cancel]  [Save Changes]                 │
└──────────────────────────────────────────┘
```

**Features:**

- Live preview updates as you type
- Full markdown syntax support
- Cancel button to discard changes
- Save button to persist changes

---

## Technical Implementation

### Database Changes

**None** - Uses existing `DocumentPage.markdown_content` field

### New API Endpoints

#### 1. Update Page Content

```
POST /documents/pages/{page_id}/edit/

Request:
{
    "markdown_content": "# New Title\n\nContent here..."
}

Response Success:
{
    "success": true,
    "message": "Page updated successfully",
    "html": "<h1>New Title</h1>\n<p>Content here...</p>",
    "page_id": 42
}

Response Error:
{
    "success": false,
    "error": "Permission denied"  // or other error message
}
```

**Permissions:**

- Only document owner can edit
- Returns 403 Forbidden if not owner
- Returns 404 Not Found if page doesn't exist

#### 2. Render Markdown Preview

```
POST /documents/pages/render-markdown/

Request:
{
    "markdown": "# Preview\n\nThis is **bold** text"
}

Response Success:
{
    "success": true,
    "html": "<h1>Preview</h1>\n<p>This is <strong>bold</strong> text</p>"
}
```

**Note:** This endpoint is public (doesn't check ownership) but is only called from the edit modal for preview purposes

### Files Modified

#### 1. `templates/document_processing/page_detail.html`

**Changes:**

- Added pagination section at bottom with Previous/Next buttons
- Added Edit button to content header (visible only to owner)
- Added edit modal with markdown input and live preview
- Added JavaScript functions for:
  - Opening/closing edit modal
  - Live preview rendering
  - Saving changes to server
  - Updating display content

**New HTML Elements:**

```html
<!-- Pagination Navigation -->
<nav aria-label="Page navigation" class="mt-4">
  <div class="d-flex justify-content-between align-items-center">
    <!-- Previous/Next buttons -->
  </div>
</nav>

<!-- Edit Modal -->
<div class="modal fade" id="editModal">
  <!-- Modal content with textarea and preview -->
</div>
```

#### 2. `document_processing/views.py`

**Changes:**

- Updated `page_detail()` view:
  - Added permission check (owner or shared user)
  - Added pagination data (total_pages, previous_url, next_url)
  - Added `can_edit` flag (true only for owner)
- Added `page_edit()` view:
  - POST endpoint for saving page content
  - Permission check (owner only)
  - Markdown to HTML conversion
  - Audit logging
- Added `render_markdown()` view:
  - POST endpoint for live preview
  - Converts markdown to HTML
  - Used by the edit modal preview

**New Imports:**

```python
import json
import markdown as md
```

#### 3. `document_processing/urls.py`

**Changes:**

- Added `pages/<int:page_id>/edit/` → `page_edit` view
- Added `pages/render-markdown/` → `render_markdown` view

---

## Usage Examples

### For Document Owner (Can Edit)

1. Navigate to any page of their document
2. Click the "Edit" button in the content header
3. Edit the markdown in the textarea
4. Preview renders live as you type
5. Click "Save Changes" or "Cancel"
6. Page updates with new content

### For Shared User (Cannot Edit)

1. Navigate to shared document page
2. No "Edit" button visible
3. Can only view the content
4. Cannot make changes

### For Non-Shared User

1. Cannot access the page at all
2. Receives 403 Forbidden error

---

## Markdown Syntax Supported

The editor supports full markdown syntax including:

````markdown
# Heading 1

## Heading 2

### Heading 3

**Bold text**
_Italic text_
`Inline code`

- Bullet point
- Another point
  - Nested point

1. Numbered item
2. Another item

[Link text](https://example.com)

```python
# Code block with syntax highlighting
def hello():
    print("world")
```
````

| Column 1 | Column 2 |
| -------- | -------- |
| Cell 1   | Cell 2   |

```

---

## Pagination Logic

### URL Structure

```

/documents/docs/{doc_id}/pages/{page_number}/

````

**Example:**
- Page 1: `/documents/docs/42/pages/1/`
- Page 2: `/documents/docs/42/pages/2/`
- Page 25: `/documents/docs/42/pages/25/`

### Previous/Next Calculation

```python
# In page_detail view
total_pages = page_obj.document.pages.count()

if page > 1:
    previous_page_url = f"/documents/docs/{doc_id}/pages/{page - 1}/"
else:
    previous_page_url = None  # Disable button

if page < total_pages:
    next_page_url = f"/documents/docs/{doc_id}/pages/{page + 1}/"
else:
    next_page_url = None  # Disable button
````

---

## JavaScript Functions

### Edit Modal Functions

**`editBtn.addEventListener('click')`**

- Opens the edit modal
- Populates textarea with current content
- Initializes preview

**`contentInput.addEventListener('input')`**

- Triggered as user types
- Calls `updatePreview()` to render live preview
- Sends markdown to server for rendering

**`saveBtn.addEventListener('click')`**

- Validates content is not empty
- Sends POST request to `/documents/pages/{page_id}/edit/`
- On success:
  - Closes modal
  - Updates page display with new HTML
  - Shows success toast
- On error:
  - Shows error toast
  - Keeps modal open for retry

### Utility Functions

**`updatePreview(markdown)`**

- Sends markdown to `/documents/pages/render-markdown/` endpoint
- Updates preview div with rendered HTML

**`updateDisplayContent(html)`**

- Updates the main page content display
- Called after successful save

---

## Error Handling

### Permission Errors

```javascript
// Response 403: Not Owner
{
    "success": false,
    "error": "Permission denied"
}
```

Shows error toast: "Permission denied"

### Empty Content Error

```javascript
// Response 400: Empty content
{
    "success": false,
    "error": "Content cannot be empty"
}
```

Shows error toast: "Content cannot be empty"

### Server Error

```javascript
// Response 500: Server error
{
    "success": false,
    "error": "An error occurred while updating the page"
}
```

Shows error toast and keeps modal open for retry

---

## Security Considerations

### 1. Ownership Check

- Only document owner can edit their pages
- Shared users cannot edit (view only for now)
- Non-shared users receive 403 Forbidden

### 2. CSRF Protection

- All POST requests include CSRF token
- Uses Django's CSRF middleware

### 3. Input Validation

- Content cannot be empty
- Markdown is sanitized by `md.markdown()` library
- No direct HTML injection possible

### 4. Audit Logging

```python
logger.info(
    f"Page {page_obj.page_number} of document '{page_obj.document.title}' "
    f"updated by user {request.user.id}"
)
```

All edits are logged with:

- Who made the change (user ID)
- Which page was changed
- Which document it belongs to

---

## Testing

### Test Edit Permission

```bash
# As document owner
curl -X POST http://localhost:8000/documents/pages/42/edit/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN" \
  -d '{"markdown_content": "# New Content"}'

# Expected: 200 OK with updated HTML
```

### Test Permission Denied

```bash
# As non-owner user (different user session)
curl -X POST http://localhost:8000/documents/pages/42/edit/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: YOUR_CSRF_TOKEN" \
  -d '{"markdown_content": "# Hacker Content"}'

# Expected: 403 Forbidden
```

### Test Pagination

```
1. Navigate to page 1: /documents/docs/42/pages/1/
   - Previous button: disabled
   - Next button: enabled (links to page 2)

2. Navigate to page 2: /documents/docs/42/pages/2/
   - Previous button: enabled (links to page 1)
   - Next button: enabled (links to page 3)

3. Navigate to last page: /documents/docs/42/pages/25/
   - Previous button: enabled (links to page 24)
   - Next button: disabled
```

---

## Future Enhancements

### 1. Shared User Editing

Currently, only owners can edit. Could be extended to:

- Allow COLLABORATOR permission to edit
- Track who edited what and when
- Add version history/rollback

### 2. Rich Text Editor

Instead of markdown textarea:

- TinyMCE or similar rich text editor
- WYSIWYG editing
- Better for non-technical users

### 3. Edit History

- Track all changes to a page
- Show who edited what and when
- Ability to revert to previous versions
- Diff view between versions

### 4. Collaborative Editing

- Real-time simultaneous editing
- Multiple users editing same page
- Cursor/presence indicators
- Conflict resolution

### 5. Comments & Suggestions

- Allow users to leave comments on pages
- Suggestion mode (like Google Docs)
- Track suggestions and resolutions

---

## Related Files

- `document_processing/models.py` - DocumentPage model
- `document_processing/views.py` - Updated page_detail, new page_edit and render_markdown views
- `document_processing/urls.py` - New URL routes
- `document_processing/templatetags/custom_tags.py` - md_to_html filter
- `templates/document_processing/page_detail.html` - UI and JavaScript
- `templates/base.html` - Base template (uses Bootstrap & Icons)

---

## Troubleshooting

### Edit button not visible

- Make sure you're logged in as the document owner
- Refresh the page
- Check browser console for JavaScript errors

### Preview not updating

- Check that `/documents/pages/render-markdown/` endpoint is accessible
- Check browser console for network errors
- Verify markdown is valid syntax

### Changes not saving

- Verify CSRF token is being sent (check HTML source for csrf token)
- Check user has owner permissions
- Check server logs for errors

### Pagination buttons disabled

- If at first page, Previous button is disabled (normal)
- If at last page, Next button is disabled (normal)
- Check document has multiple pages

---

**Created:** November 2, 2025  
**Version:** 1.0
