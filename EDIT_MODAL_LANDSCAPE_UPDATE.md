# Edit Modal Layout Update - Landscape Mode for Desktop

## Summary of Changes

The edit modal in the page detail view has been updated to use a **landscape layout** on desktop screens (editor on left, preview on right), while maintaining the **vertical stacked layout** on mobile screens.

---

## What Changed

### Before

- **Layout**: Vertical stacked (editor on top, preview below)
- **Size**: `modal-lg` (fixed width)
- **Mobile**: Same vertical layout on all screen sizes
- **Preview Container**: Separate `mb-3` div below editor

### After

- **Layout**:
  - **Desktop (lg and above)**: Side-by-side landscape (50/50 split)
  - **Mobile (below lg)**: Vertical stacked (original behavior)
- **Size**: `modal-xl` with fullscreen-lg-down for responsive behavior
- **Mobile**: Fullscreen on small devices
- **Editor & Preview**: Both use flexbox to fill available space

---

## Technical Details

### Modal Dialog Changes

```html
<!-- Before -->
<div class="modal-dialog modal-lg">
  <!-- After -->
  <div
    class="modal-dialog modal-fullscreen-lg-down modal-xl"
    style="max-height: 90vh;"
  ></div>
</div>
```

**Explanation:**

- `modal-xl`: Makes modal extra large (good for landscape layout)
- `modal-fullscreen-lg-down`: Fullscreen on mobile devices (below `lg` breakpoint)
- `max-height: 90vh`: Prevents modal from exceeding 90% of viewport height

### Modal Content Structure

```html
<!-- Before -->
<div class="modal-content bg-secondary">
  <div class="modal-body">
    <div class="mb-3">
      <!-- Editor -->
    </div>
    <div id="previewContainer" class="mb-3">
      <!-- Preview -->
    </div>
  </div>
</div>

<!-- After -->
<div class="modal-content bg-secondary h-100 d-flex flex-column">
  <div class="modal-body flex-grow-1 overflow-hidden p-3">
    <div class="row h-100 g-3">
      <div class="col-lg-6">
        <!-- Editor -->
      </div>
      <div class="col-lg-6">
        <!-- Preview -->
      </div>
    </div>
  </div>
</div>
```

**Explanation:**

- `h-100 d-flex flex-column`: Makes modal content flex container to use full height
- `flex-grow-1 overflow-hidden`: Editor/preview area grows to fill available space
- `row h-100`: Grid row that uses full height
- `col-lg-6`: Each section takes 50% on large screens, stacks on mobile
- `g-3`: Gap between columns (15px spacing)

### Editor & Preview Container

```html
<!-- Editor -->
<div class="col-lg-6 d-flex flex-column">
  <label>...</label>
  <textarea
    class="form-control flex-grow-1"
    style="resize: none; font-family: monospace;"
  >
  </textarea>
  <small>...</small>
</div>

<!-- Preview -->
<div class="col-lg-6 d-flex flex-column">
  <label>...</label>
  <div
    id="previewContent"
    class="flex-grow-1 overflow-auto"
    style="max-height: 100%;"
  ></div>
</div>
```

**Explanation:**

- `d-flex flex-column`: Makes container a flex column
- `flex-grow-1`: Textarea/preview grows to fill available space
- `overflow-auto`: Adds scroll if content exceeds container
- `resize: none`: Prevents manual textarea resizing (we control it with flex)
- `font-family: monospace`: Better for code editing
- `font-size: 0.95rem`: Slightly smaller for fitting more content

---

## Responsive Behavior

### Desktop (≥992px - `lg` breakpoint)

```
┌─────────────────────────────────────────────┐
│ Edit Modal                              [X] │
├─────────────────────────────────────────────┤
│                                             │
│  Editor (50%)  │  Preview (50%)            │
│  textarea      │  Rendered markdown        │
│                │                           │
│  ↓↓↓↓↓↓↓↓↓↓↓  │  ↓↓↓↓↓↓↓↓↓↓↓            │
│  ↓↓↓↓↓↓↓↓↓↓↓  │  **Bold text**            │
│  ↓↓↓↓↓↓↓↓↓↓↓  │  - List item              │
│                │                           │
├─────────────────────────────────────────────┤
│ [Cancel]                      [Save Changes]│
└─────────────────────────────────────────────┘
```

### Mobile (<992px)

```
┌──────────────────┐
│ Edit Modal   [X] │
├──────────────────┤
│                  │
│  Markdown Content│
│  ──────────────  │
│  [textarea]      │
│  [textarea]      │
│  [textarea]      │
│                  │
│  Live Preview    │
│  ──────────────  │
│  [preview]       │
│  [preview]       │
│  [preview]       │
│                  │
├──────────────────┤
│[Cancel] [Save]   │
└──────────────────┘
```

---

## Key Features

### 1. **Full-Screen Mobile**

- Modal becomes fullscreen on mobile devices (below `lg` breakpoint)
- Uses entire viewport for better usability on small screens
- `modal-fullscreen-lg-down` handles this automatically

### 2. **Side-by-Side Desktop**

- Editor and preview side-by-side for better workflow
- 50/50 split using Bootstrap grid (`col-lg-6`)
- Both areas grow/shrink with viewport

### 3. **Responsive Height**

- Modal constrained to `90vh` max-height
- Content scrolls if needed
- Header/footer always visible

### 4. **Scrollable Sections**

- Editor (textarea): Grows with flex, scrolls if needed
- Preview: `overflow-auto` allows independent scrolling
- Both sections scroll independently

### 5. **Better Code Editing**

- Monospace font for better code visualization
- Textarea resize disabled (controlled by flex layout)
- Larger font size (0.95rem) for readability
- More rows available on landscape mode

---

## CSS Classes Used

| Class                      | Purpose                          |
| -------------------------- | -------------------------------- |
| `modal-fullscreen-lg-down` | Fullscreen below `lg` breakpoint |
| `modal-xl`                 | Extra large modal size           |
| `h-100`                    | Height 100% of parent            |
| `d-flex`                   | Display flex                     |
| `flex-column`              | Flex direction column            |
| `flex-grow-1`              | Grow to fill available space     |
| `overflow-hidden`          | Hide overflow                    |
| `overflow-auto`            | Auto scroll if needed            |
| `col-lg-6`                 | 50% width on large screens       |
| `g-3`                      | Gap between grid items           |

---

## Browser Compatibility

✅ **Full support** in all modern browsers:

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

---

## Testing Checklist

- [ ] **Desktop (1200px+)**: Modal shows editor left, preview right
- [ ] **Tablet (768px-991px)**: Modal switches to vertical stacked
- [ ] **Mobile (< 768px)**: Modal goes fullscreen
- [ ] **Editor scrolls**: Long markdown content scrolls in textarea
- [ ] **Preview scrolls**: Long rendered content scrolls independently
- [ ] **Responsive text**: Text remains readable at different sizes
- [ ] **Modal fits**: Header/footer visible, doesn't exceed viewport
- [ ] **Save button**: Works on all screen sizes
- [ ] **Live preview**: Updates in real-time as you type

---

## Example Usage

The modal works exactly the same from the user's perspective:

1. Click "Edit" button
2. Modal opens with editor and preview
3. Type or paste markdown in the editor
4. See live preview update on the right (or below on mobile)
5. Click "Save Changes" to save
6. Or "Cancel" to discard changes

---

## Notes

- The layout automatically adapts based on screen size
- No JavaScript changes were needed
- Pure CSS/Bootstrap implementation
- Maintains all existing functionality
- Full backward compatibility

---

## Future Enhancements

Possible improvements:

- Add syntax highlighting to textarea using a library like Prism.js
- Add markdown cheat sheet panel
- Add keyboard shortcut for save (Ctrl+S / Cmd+S)
- Add undo/redo functionality
- Add character/word count
- Add auto-save feature
