# Task: Improve "Copy Prompt" Functionality in Storyboard

## 1. Issue Description
Currently, in the Storyboard page (`pages/8_📋_스토리보드.py`), when a user views an image in the expanded modal (handled by `utils/image_viewer.py`), the **"Copy Prompt" ("프롬프트 복사")** button functions inefficiently. 
- **Current Behavior:** Clicking the button does not copy the text. Instead, it displays the prompt in a `st.code()` block, requiring the user to manually select and copy the text.
- **Desired Behavior:** Clicking the button should **automatically** copy the full, untruncated prompt text to the system clipboard and show a confirmation message (e.g., Toast), without displaying a code block.

## 2. Target Files
- `utils/image_viewer.py`: This is the primary file containing the `show_image_modal` function where the "Copy Prompt" button is defined.
- `pages/8_📋_스토리보드.py` (Reference): Contains an existing implementation of `copy_path_to_clipboard` which can be adapted.

## 3. Detailed Implementation Steps

### Step 1: Create/Refactor Clipboard Utility
There is likely an existing function `copy_path_to_clipboard` in `pages/8_📋_스토리보드.py` (lines ~373). We need to make this a generic, reusable utility.

**Action:**
1.  Check if `utils/common_utils.py` or a similar shared utility file exists. If so, add the clipboard function there. If not, add it to `utils/image_viewer.py` or keep it where it is but make it importable and generic.
2.  Define a function `copy_text_to_clipboard(text: str)`:
    -   It should accept any string `text`.
    -   It should use `streamlit.components.v1.html` to inject JavaScript.
    -   **Important:** Properly escape Python strings for JavaScript (handle newlines, backslashes, and quotes).
    -   The JavaScript should use `navigator.clipboard.writeText(text)`.

**Example Implementation Pattern:**
```python
import streamlit.components.v1 as components
import json

def copy_text_to_clipboard(text: str):
    """
    Copies the provided text to the clipboard using JavaScript.
    """
    # Use json.dumps to safely escape the string for JS
    escaped_text = json.dumps(text)
    
    js_code = f"""
    <script>
    (function() {{
        const text = {escaped_text};
        navigator.clipboard.writeText(text).then(function() {{
            console.log('Copy succeeded');
        }}).catch(function(err) {{
            console.error('Copy failed', err);
        }});
    }})();
    </script>
    """
    components.html(js_code, height=0)
```

### Step 2: Update `utils/image_viewer.py`
Locate the `show_image_modal` function (around line 135) and the specific button logic (around line 197).

**Current Logic:**
```python
if st.button("프롬프트 복사", key="copy_prompt_modal"):
    st.code(prompt_to_show)
    st.success("위 텍스트를 선택하여 복사하세요!")
```

**New Logic:**
1. Remove `st.code(prompt_to_show)`.
2. Call the `copy_text_to_clipboard(prompt_to_show)` function inside the button click block.
3. Use `st.toast("프롬프트가 클립보드에 복사되었습니다!")` for a cleaner feedback loop instead of `st.success`.

### Step 3: Verify & Polish
- Ensure the prompt text is **not truncated**. The full `prompt_to_show` string must be passed.
- Ensure the component structure does not cause layout shifts (keep `height=0` for the JS component).
- Verify the button works inside the `st.dialog` (modal).

## 4. Constraint Checklist
- [ ] Must use JavaScript injection for clipboard access (Streamlit restriction).
- [ ] Must handle multi-line prompts correctly.
- [ ] Must provide visual feedback (Toast).
- [ ] Must NOT show the raw text in a code block anymore.
