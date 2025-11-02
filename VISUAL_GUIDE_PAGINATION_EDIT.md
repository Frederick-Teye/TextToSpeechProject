# Visual Guide: Page Pagination & Edit Feature

## 1. Page Detail View (Before Editing)

```
┌─────────────────────────────────────────────────────────────────┐
│ TTS Project - Document Processing                       [Menu]  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ Page 1 - My Document                                             │
│                                                    [← Back]       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│ Content                                              [✏️ Edit]   │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │                                                             │ │
│ │ # Chapter 1: Introduction                                 │ │
│ │                                                             │ │
│ │ This is the introduction to our document. It explains      │ │
│ │ the key concepts and provides an overview of what you      │ │
│ │ will learn in this chapter.                               │ │
│ │                                                             │ │
│ │ ## 1.1 Background                                         │ │
│ │                                                             │ │
│ │ Some background information...                             │ │
│ │                                                             │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
├─────────────────────────────────────────────────────────────────┤
│ PAGINATION:                                                      │
│                                                                   │
│    [◀ Previous Page]  Page 1 of 5  [Next Page ▶]                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Click Edit Button

```
┌─────────────────────────────────────────────────────────────────┐
│ MODAL APPEARS:                                                   │
│                                                                   │
│ ╔═══════════════════════════════════════════════════════════╗   │
│ ║ ✏️ Edit Page 1                                         [×]║   │
│ ╠═══════════════════════════════════════════════════════════╣   │
│ ║                                                           ║   │
│ ║ Markdown Content                                         ║   │
│ ║ ┌─────────────────────────────────────────────────────┐ ║   │
│ ║ │ # Chapter 1: Introduction                          │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ This is the introduction to our document. It      │ ║   │
│ ║ │ explains the key concepts and provides an         │ ║   │
│ ║ │ overview of what you will learn in this chapter.  │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ ## 1.1 Background                                 │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ Some background information...                     │ ║   │
│ ║ │                                                     │ ║   │
│ ║ └─────────────────────────────────────────────────────┘ ║   │
│ ║                                                           ║   │
│ ║ Preview                                                  ║   │
│ ║ ┌─────────────────────────────────────────────────────┐ ║   │
│ ║ │ Chapter 1: Introduction                           │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ This is the introduction to our document. It      │ ║   │
│ ║ │ explains the key concepts and provides an         │ ║   │
│ ║ │ overview of what you will learn in this chapter.  │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ 1.1 Background                                    │ ║   │
│ ║ │ Some background information...                     │ ║   │
│ ║ │                                                     │ ║   │
│ ║ └─────────────────────────────────────────────────────┘ ║   │
│ ║                                                           ║   │
│ ╠═══════════════════════════════════════════════════════════╣   │
│ ║ [Cancel]              [✅ Save Changes]                  ║   │
│ ╚═══════════════════════════════════════════════════════════╝   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## 3. Edit Content (Live Preview Updates)

```
User types in textarea:
# Chapter 1: Introduction [Updated!]

│
└─ AJAX Request to /documents/pages/render-markdown/
   │
   └─ Server renders markdown to HTML
      │
      └─ Preview updates in real-time!

┌─────────────────────────────────────────────────────────────────┐
│ ║ Preview                                                  ║   │
│ ║ ┌─────────────────────────────────────────────────────┐ ║   │
│ ║ │ Chapter 1: Introduction [Updated!]               │ ║   │
│ ║ │                                                     │ ║   │
│ ║ │ This is the introduction to our document...        │ ║   │
│ ║ └─────────────────────────────────────────────────────┘ ║   │
└─────────────────────────────────────────────────────────────────┘
```

## 4. Save Changes

```
Click [✅ Save Changes] button:

│
└─ AJAX Request to /documents/pages/{page_id}/edit/
   Body: { "markdown_content": "# Chapter 1: Introduction..." }
   │
   ├─ Server verifies user is owner ✅
   ├─ Saves content to database ✅
   ├─ Returns HTML preview ✅
   │
   └─ Response:
      {
        "success": true,
        "html": "<h1>Chapter 1: Introduction...</h1>...",
        "message": "Page updated successfully"
      }

Result:
┌─ Modal closes
├─ Toast notification: "✅ Page updated successfully!"
└─ Page content updates with new HTML
```

## 5. Pagination Navigation

### At Page 1 of 5:

```
[◀ Previous Page] (disabled)   Page 1 of 5   [Next Page ▶] (enabled)
      │                                              │
      └─ Grayed out, no action             └─ Links to Page 2
```

### At Page 3 of 5:

```
[◀ Previous Page] (enabled)   Page 3 of 5   [Next Page ▶] (enabled)
      │                                              │
      └─ Links to Page 2              └─ Links to Page 4
```

### At Page 5 of 5:

```
[◀ Previous Page] (enabled)   Page 5 of 5   [Next Page ▶] (disabled)
      │                                              │
      └─ Links to Page 4                    └─ Grayed out, no action
```

## 6. Keyboard Shortcuts (Future Enhancement)

```
Ctrl+E    - Open edit modal
Esc       - Close modal
Ctrl+S    - Save changes (when modal is open)
←/→       - Previous/Next page (if implemented)
```

## 7. Permission Matrix

### Document Owner:

```
Page Detail View:
├─ View content          ✅
├─ Edit button visible   ✅
├─ Can edit content      ✅
├─ Can save changes      ✅
├─ Navigate pages        ✅
└─ Audit logs save       ✅
```

### Shared User (Any Permission):

```
Page Detail View:
├─ View content          ✅
├─ Edit button visible   ❌
├─ Can edit content      ❌
├─ Can save changes      ❌
├─ Navigate pages        ✅
└─ Audit logs save       ❌
```

### Non-Shared User:

```
Page Detail View:
├─ View content          ❌ (403 Forbidden)
├─ Edit button visible   ❌
├─ Can edit content      ❌
├─ Can save changes      ❌
├─ Navigate pages        ❌
└─ Audit logs save       ❌
```

## 8. Error Scenarios

### Error: Empty Content

```
User clicks [Save Changes] without any content

│
└─ Client validation fails
   │
   └─ Toast: "❌ Content cannot be empty"
   └─ Modal stays open
```

### Error: Not Owner

```
Non-owner tries to POST /documents/pages/42/edit/

│
└─ Server permission check fails
   │
   └─ Response: 403 Forbidden
      {
        "success": false,
        "error": "Permission denied"
      }
   └─ Toast: "❌ Permission denied"
```

### Error: Page Not Found

```
User navigates to /documents/docs/42/pages/999/

│
└─ Server queries for page 999
   │
   └─ Page not found
   └─ Response: 404 Not Found
   └─ Django shows 404 page
```

## 9. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERACTION                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
              ┌─────▼─────┐         ┌─────▼──────┐
              │ Click Edit │         │ Click Next │
              └─────┬─────┘         └─────┬──────┘
                    │                     │
        ┌───────────┴────────────┐        │
        │                        │        │
   ┌────▼─────────┐      ┌──────▼───────┐│
   │ Modal opens  │      │ Load Page N+1││
   │ Show content │      │ from server  ││
   └────┬─────────┘      └──────┬───────┘│
        │                       │        │
   ┌────▼──────────┐       ┌────▼───────┘
   │ User types    │       │
   │ markdown      │       │ Render template with:
   │ in textarea   │       │ - page content
   └────┬──────────┘       │ - pagination data
        │                  │ - can_edit flag
   ┌────▼──────────────┐   │
   │ Preview updates   │   └────────────┬────────────┐
   │ (Live rendering)  │                │            │
   └────┬──────────────┘           ┌────▼──┐     ┌──▼──────┐
        │                          │ Page  │     │ Previous│
   ┌────▼──────────────┐           │ View  │     │ Button  │
   │ Click Save        │           └───────┘     └─────────┘
   │ Changes           │
   └────┬──────────────┘
        │
   ┌────▼──────────────────────────┐
   │ POST /documents/pages/XX/edit/ │
   │ Body: { markdown_content }     │
   └────┬──────────────────────────┘
        │
   ┌────▼──────────────────────────┐
   │ Server:                        │
   │ 1. Check ownership             │
   │ 2. Validate input              │
   │ 3. Save to database            │
   │ 4. Log audit trail             │
   │ 5. Render HTML                 │
   │ 6. Return response             │
   └────┬──────────────────────────┘
        │
   ┌────▼──────────────────┐
   │ Update page display   │
   │ Close modal           │
   │ Show toast message    │
   └───────────────────────┘
```

## 10. File Structure

```
templates/
└── document_processing/
    └── page_detail.html           ← Template (updated)
        ├── Pagination section
        ├── Edit button
        ├── Edit modal
        ├── Edit JavaScript
        └── Toast notifications

document_processing/
├── views.py                       ← Views (updated)
│   ├── page_detail()              ← Updated with pagination
│   ├── page_edit()                ← New endpoint
│   └── render_markdown()          ← New endpoint
├── urls.py                        ← URLs (updated)
│   ├── pages/<int:page_id>/edit/
│   └── pages/render-markdown/
└── models.py                      ← No changes (uses existing)
    └── DocumentPage.markdown_content
```

---

## Summary Table

| Feature              | Status      | Location                  | Endpoint                                  |
| -------------------- | ----------- | ------------------------- | ----------------------------------------- |
| Pagination Buttons   | ✅ Complete | page_detail.html (bottom) | N/A (links to /documents/docs/X/pages/Y/) |
| Previous Page Button | ✅ Complete | page_detail.html          | Navigates to page N-1                     |
| Next Page Button     | ✅ Complete | page_detail.html          | Navigates to page N+1                     |
| Edit Button          | ✅ Complete | page_detail.html (header) | Opens modal                               |
| Edit Modal           | ✅ Complete | page_detail.html          | Modal popup                               |
| Markdown Textarea    | ✅ Complete | Edit modal                | Input field                               |
| Live Preview         | ✅ Complete | Edit modal                | /documents/pages/render-markdown/         |
| Save Changes         | ✅ Complete | Edit modal                | /documents/pages/{id}/edit/               |
| Cancel Button        | ✅ Complete | Edit modal                | Closes modal                              |
| Toast Notifications  | ✅ Complete | page_detail.html          | Success/error messages                    |
| Permission Check     | ✅ Complete | views.py                  | Owner only for edit                       |
| Audit Logging        | ✅ Complete | views.py                  | Logs all edits                            |

---

**Created:** November 2, 2025  
**Status:** Ready for use! 🚀
