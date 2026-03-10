"""Browser task definitions for Skyvern integration.

Uses the-internet.herokuapp.com — a stable public test site. Tasks are
designed to exploit real browser-agent failure modes:

- Deliberately vague prompts that omit critical interaction details
- Multi-step workflows requiring page navigation + state tracking
- JS alerts/prompts that block execution if not handled
- Nested iframes that break standard element targeting
- Drag-and-drop and hover interactions that need non-obvious approaches
- Tight step limits that punish wasted actions

Each pattern appears twice: an original task and a "learning check" variant.
The learning check tests whether lessons extracted from the original failure
transfer to a structurally similar but visually different task.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskValidation:
    """How to evaluate a Skyvern task result."""

    mode: str  # "status_only" | "data_extraction"
    data_extraction_schema: dict | None = None
    expected_data: dict | None = None  # partial match against extracted output


@dataclass
class BrowserTask:
    """A browser automation task for Skyvern to execute."""

    id: str
    title: str
    url: str
    prompt: str
    max_steps: int
    validation: TaskValidation
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 8 tasks: 4 failure-prone patterns x 2 (original + learning check)
#
# Pattern 1: JS Alerts — agents try to interact with the page while a JS
#   dialog is blocking. Must dismiss the dialog first.
# Pattern 2: Nested Iframes — standard selectors can't reach elements
#   inside iframes. Agent must switch context.
# Pattern 3: Multi-step with state — requires navigating across pages
#   while remembering data from a previous page.
# Pattern 4: Deliberately vague prompt — omits key details the agent
#   must discover by reading the page itself.
# ---------------------------------------------------------------------------

TASK_LIST: list[BrowserTask] = [
    # -----------------------------------------------------------------------
    # Pattern 1: JS Alert handling
    # Agents commonly fail because JS confirm/prompt dialogs block all
    # interaction. The agent must handle the dialog before proceeding.
    # -----------------------------------------------------------------------
    BrowserTask(
        id="js-alert-confirm",
        title="Trigger JS confirm and capture result text",
        url="https://the-internet.herokuapp.com/javascript_alerts",
        prompt=(
            "On this page there are buttons that trigger JavaScript dialogs. "
            "Click the button that triggers a JS Confirm dialog. "
            "When the dialog appears, accept it (click OK). "
            "Then read the result message that appears on the page and extract it."
        ),
        max_steps=8,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "result_text": {
                        "type": "string",
                        "description": "The result message displayed on the page after handling the dialog",
                    },
                },
            },
            expected_data={"result_text": "You clicked: Ok"},
        ),
        tags=["js-alerts", "dialogs", "confirm"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 2: Nested Iframes
    # Elements inside iframes are invisible to standard selectors.
    # Agent must identify and switch into the correct frame context.
    # -----------------------------------------------------------------------
    BrowserTask(
        id="nested-frames-extract",
        title="Extract text from nested iframes",
        url="https://the-internet.herokuapp.com/nested_frames",
        prompt=(
            "This page contains nested iframes. There is a top frame divided into "
            "left, middle, and right sections, and a bottom frame. "
            "Extract the text content from the MIDDLE frame."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "middle_frame_text": {
                        "type": "string",
                        "description": "The text content found inside the middle frame",
                    },
                },
            },
            expected_data={"middle_frame_text": "MIDDLE"},
        ),
        tags=["iframes", "nested-frames", "context-switching"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 3: Multi-step with state tracking
    # Agent must navigate through multiple pages, remembering information
    # from earlier steps to complete the final action.
    # -----------------------------------------------------------------------
    BrowserTask(
        id="login-then-secure-content",
        title="Login and extract secure area content",
        url="https://the-internet.herokuapp.com/login",
        prompt=(
            "First, log in using username 'tomsmith' and password 'SuperSecretPassword!'. "
            "After logging in successfully, you will be redirected to a secure area. "
            "On that secure area page, extract the main heading text (the h2 element) "
            "AND the full text of the flash message that confirms login. "
            "Do NOT log out."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "secure_heading": {
                        "type": "string",
                        "description": "The h2 heading text on the secure area page",
                    },
                    "flash_message": {
                        "type": "string",
                        "description": "The flash success message after login",
                    },
                },
            },
            expected_data={
                "secure_heading": "Secure Area",
                "flash_message": "You logged into a secure area!",
            },
        ),
        tags=["multi-step", "login", "state-tracking", "navigation"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 4: Deliberately vague — agent must discover page structure
    # Prompt gives minimal info. Agent must read the page, understand
    # the interface, and figure out the right interaction.
    # -----------------------------------------------------------------------
    BrowserTask(
        id="sortable-table-query",
        title="Find the highest-paid person in the table",
        url="https://the-internet.herokuapp.com/tables",
        prompt=(
            "There are tables on this page. Look at the SECOND table (Example 2). "
            "Sort the table by the 'Due' column (highest first) by clicking the column header. "
            "After sorting, extract the last name of the person in the FIRST row "
            "(who should have the highest due amount) and their due amount."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "last_name": {
                        "type": "string",
                        "description": "Last name of the person with the highest due",
                    },
                    "due_amount": {
                        "type": "string",
                        "description": "The due amount (e.g., '$100.00')",
                    },
                },
            },
            # After sorting Due descending, Conway ($100.00) should be first
            expected_data={"last_name": "Conway", "due_amount": "$100.00"},
        ),
        tags=["tables", "sorting", "data-extraction", "multi-step"],
    ),

    # -----------------------------------------------------------------------
    # LEARNING CHECKS — structurally similar to patterns 1-4 above
    # -----------------------------------------------------------------------

    # Learning check for Pattern 1: JS Prompt (more complex than confirm)
    BrowserTask(
        id="js-alert-prompt",
        title="Handle JS prompt dialog and verify custom input",
        url="https://the-internet.herokuapp.com/javascript_alerts",
        prompt=(
            "Click the button that triggers a JS Prompt. "
            "When the prompt dialog appears, type 'Engram' into the input field, "
            "then accept it. "
            "Extract the result text shown on the page after dismissing the prompt."
        ),
        max_steps=8,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "result_text": {
                        "type": "string",
                        "description": "The result message displayed after the prompt was handled",
                    },
                },
            },
            expected_data={"result_text": "You entered: Engram"},
        ),
        tags=["js-alerts", "dialogs", "prompt", "learning-check"],
    ),

    # Learning check for Pattern 2: Single iframe (simpler but same concept)
    BrowserTask(
        id="iframe-editor-extract",
        title="Extract text from WYSIWYG editor inside iframe",
        url="https://the-internet.herokuapp.com/iframe",
        prompt=(
            "This page has a WYSIWYG text editor. The editor content is inside an iframe. "
            "Extract whatever text is currently displayed in the editor area. "
            "The editor is a TinyMCE component — the editable content is in an iframe, "
            "not directly in the page DOM."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "editor_content": {
                        "type": "string",
                        "description": "The text content currently in the WYSIWYG editor",
                    },
                },
            },
            expected_data={"editor_content": "Your content goes here."},
        ),
        tags=["iframes", "wysiwyg", "editor", "learning-check"],
    ),

    # Learning check for Pattern 3: Multi-step with form + verify
    BrowserTask(
        id="digest-auth-flow",
        title="Navigate to Digest Auth page and verify access",
        url="https://the-internet.herokuapp.com",
        prompt=(
            "Starting from the main page, find and click the link to 'Digest Authentication'. "
            "The page requires HTTP Digest Auth with credentials admin/admin. "
            "Navigate to the URL with credentials embedded: "
            "https://admin:admin@the-internet.herokuapp.com/digest_auth "
            "Extract the success message from the page."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "success_message": {
                        "type": "string",
                        "description": "The success/congratulations message on the page",
                    },
                    "authenticated": {
                        "type": "boolean",
                        "description": "Whether authentication succeeded",
                    },
                },
            },
            expected_data={"authenticated": True},
        ),
        tags=["multi-step", "authentication", "digest-auth", "navigation", "learning-check"],
    ),

    # Learning check for Pattern 4: Vague prompt requiring page discovery
    BrowserTask(
        id="broken-images-count",
        title="Count the broken images on the page",
        url="https://the-internet.herokuapp.com/broken_images",
        prompt=(
            "This page shows several images. Some of them are broken (they fail to load). "
            "Figure out how many images are on the page total, and how many are broken. "
            "A broken image typically shows a placeholder or fails to render."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "total_images": {
                        "type": "integer",
                        "description": "Total number of images on the page",
                    },
                    "broken_count": {
                        "type": "integer",
                        "description": "Number of broken/failed images",
                    },
                },
            },
            expected_data={"broken_count": 2},
        ),
        tags=["images", "broken-content", "page-analysis", "learning-check"],
    ),
]

# Learning pairs: task index → paired task index
LEARNING_PAIRS = [
    (0, 4, "JS Dialogs (confirm → prompt with input)"),
    (1, 5, "Iframes (nested frames → WYSIWYG editor)"),
    (2, 6, "Multi-Step Auth (login+extract → digest auth)"),
    (3, 7, "Page Analysis (table sorting → broken images)"),
]
