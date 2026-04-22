"""Browser task definitions for Skyvern + Engram demo.

Uses the-internet.herokuapp.com — a stable public test site.

DESIGN PHILOSOPHY: Tasks use deliberately vague or misleading prompts
that cause Skyvern to make specific, CORRECTABLE mistakes. When lessons
are extracted from Round 1 failures, they provide actionable guidance
that improves Round 2+ performance. This demonstrates the learning loop.

Key failure modes exploited:
- Ambiguous element references (which table? which checkbox?)
- Missing wait/timing instructions for dynamic content
- Wrong assumptions about default page state
- Incomplete multi-step instructions that skip critical details

Each pattern appears twice: an "explorer" task (likely to fail or
partially succeed) and a "learning check" (structurally similar,
should benefit from lessons learned on the explorer).
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
# 8 tasks: 4 failure-prone patterns x 2 (explorer + learning check)
#
# Pattern 1: Ambiguous table query — agent picks the wrong table or
#   doesn't sort before extracting, getting wrong data.
# Pattern 2: Dynamic content timing — agent extracts before the
#   content has loaded, getting empty/stale data.
# Pattern 3: Checkbox state verification — agent doesn't check
#   the default state before acting, producing wrong results.
# Pattern 4: Dropdown + verification — agent selects but doesn't
#   verify what's actually selected, or picks wrong option.
# ---------------------------------------------------------------------------

TASK_LIST: list[BrowserTask] = [
    # -----------------------------------------------------------------------
    # Pattern 1: Ambiguous table query
    # The page has TWO tables. The prompt says "the table" without
    # specifying which one. Agents typically pick Table 1 (first in DOM)
    # but the answer is in Table 2. Lesson: "use Example 2 / Table 2."
    # -----------------------------------------------------------------------
    BrowserTask(
        id="table-ambiguous-lookup",
        title="Find who owes the most in the data table",
        url="https://the-internet.herokuapp.com/tables",
        prompt=(
            "There is a data table on this page showing people and amounts due. "
            "Find the person who owes the MOST money. "
            "Extract their last name and the due amount."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "last_name": {
                        "type": "string",
                        "description": "Last name of the person who owes the most",
                    },
                    "due_amount": {
                        "type": "string",
                        "description": "The due amount (e.g., '$100.00')",
                    },
                },
            },
            # Conway owes $100.00 — highest in either table
            expected_data={"last_name": "Conway", "due_amount": "$100.00"},
        ),
        tags=["tables", "ambiguity", "data-extraction"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 2: Dynamic content — must wait for loading
    # Agent needs to click "Start", WAIT for loading to finish, then
    # extract text. Without waiting, it gets nothing or "Loading..."
    # Lesson: "click Start and wait 5+ seconds for loading to complete."
    # -----------------------------------------------------------------------
    BrowserTask(
        id="dynamic-loading-extract",
        title="Extract the dynamically loaded text",
        url="https://the-internet.herokuapp.com/dynamic_loading/1",
        prompt=(
            "This page has a Start button. There is hidden text that will appear. "
            "Get the hidden text to appear and extract it."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "loaded_text": {
                        "type": "string",
                        "description": "The text that appears after loading completes",
                    },
                },
            },
            expected_data={"loaded_text": "Hello World!"},
        ),
        tags=["dynamic-content", "timing", "loading"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 3: Checkbox state — must check before toggling
    # The page has 2 checkboxes. Checkbox 1 is unchecked, checkbox 2
    # is checked by default. Prompt asks to "make sure checkbox 1 is
    # checked and checkbox 2 is unchecked." Agent often toggles wrong
    # ones or doesn't verify the default state.
    # Lesson: "checkbox 2 starts CHECKED — uncheck it; checkbox 1
    # starts UNCHECKED — check it."
    # -----------------------------------------------------------------------
    BrowserTask(
        id="checkbox-state-management",
        title="Set checkboxes to specific states",
        url="https://the-internet.herokuapp.com/checkboxes",
        prompt=(
            "There are checkboxes on this page. "
            "Make sure checkbox 1 is CHECKED and checkbox 2 is UNCHECKED. "
            "Then report the final state of both checkboxes."
        ),
        max_steps=8,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "checkbox_1_checked": {
                        "type": "boolean",
                        "description": "Whether checkbox 1 is checked after your actions",
                    },
                    "checkbox_2_checked": {
                        "type": "boolean",
                        "description": "Whether checkbox 2 is checked after your actions",
                    },
                },
            },
            expected_data={
                "checkbox_1_checked": True,
                "checkbox_2_checked": False,
            },
        ),
        tags=["checkboxes", "state-management", "verification"],
    ),

    # -----------------------------------------------------------------------
    # Pattern 4: Dropdown selection + read-back
    # Agent must select a specific option AND verify the selection.
    # Common failure: agent reports what it *tried* to select, not what
    # is actually selected. Or it reads the placeholder as a selection.
    # Lesson: "verify the selection by re-reading the dropdown value
    # after selecting."
    # -----------------------------------------------------------------------
    BrowserTask(
        id="dropdown-select-verify",
        title="Select Option 2 from dropdown and verify",
        url="https://the-internet.herokuapp.com/dropdown",
        prompt=(
            "There is a dropdown on this page. "
            "Select 'Option 2' from the dropdown. "
            "After selecting, read back what option is currently selected "
            "and also tell me how many total options are available."
        ),
        max_steps=8,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "selected_option": {
                        "type": "string",
                        "description": "The currently selected option text",
                    },
                    "total_options": {
                        "type": "integer",
                        "description": "Total number of selectable options (not counting placeholder)",
                    },
                },
            },
            expected_data={
                "selected_option": "Option 2",
                "total_options": 2,
            },
        ),
        tags=["dropdown", "selection", "verification"],
    ),

    # -----------------------------------------------------------------------
    # LEARNING CHECKS — structurally similar to patterns 1-4
    # These should benefit from lessons learned in the first 4 tasks.
    # -----------------------------------------------------------------------

    # Learning check for Pattern 1: Same table page, different query
    # Lesson from task 1 should help agent know which table to use and
    # that sorting is needed.
    BrowserTask(
        id="table-sort-and-extract",
        title="Find the person with the lowest due amount",
        url="https://the-internet.herokuapp.com/tables",
        prompt=(
            "Look at the data table showing people and amounts. "
            "Find the person who owes the LEAST money. "
            "Extract their last name and the due amount."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "last_name": {
                        "type": "string",
                        "description": "Last name of the person who owes the least",
                    },
                    "due_amount": {
                        "type": "string",
                        "description": "The due amount (e.g., '$25.00')",
                    },
                },
            },
            # Bach owes $25.00 — lowest in either table
            expected_data={"last_name": "Bach", "due_amount": "$25.00"},
        ),
        tags=["tables", "sorting", "data-extraction", "learning-check"],
    ),

    # Learning check for Pattern 2: Same dynamic loading, different example
    # Lesson from task 2 about waiting for content should transfer directly.
    BrowserTask(
        id="dynamic-loading-example2",
        title="Extract dynamically rendered text (Example 2)",
        url="https://the-internet.herokuapp.com/dynamic_loading/2",
        prompt=(
            "This page has content that will be dynamically added. "
            "Trigger the content to load and extract the text that appears."
        ),
        max_steps=10,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "loaded_text": {
                        "type": "string",
                        "description": "The text that appears after loading completes",
                    },
                },
            },
            expected_data={"loaded_text": "Hello World!"},
        ),
        tags=["dynamic-content", "timing", "loading", "learning-check"],
    ),

    # Learning check for Pattern 3: Same checkboxes, opposite goal
    # Lesson about default states should help agent get it right.
    BrowserTask(
        id="checkbox-verify-defaults",
        title="Verify and report checkbox default states",
        url="https://the-internet.herokuapp.com/checkboxes",
        prompt=(
            "There are checkboxes on this page. WITHOUT clicking anything, "
            "report the default state of each checkbox — which ones are "
            "checked and which are unchecked when the page first loads."
        ),
        max_steps=5,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "checkbox_1_checked": {
                        "type": "boolean",
                        "description": "Whether checkbox 1 is checked by default",
                    },
                    "checkbox_2_checked": {
                        "type": "boolean",
                        "description": "Whether checkbox 2 is checked by default",
                    },
                },
            },
            expected_data={
                "checkbox_1_checked": False,
                "checkbox_2_checked": True,
            },
        ),
        tags=["checkboxes", "state-verification", "defaults", "learning-check"],
    ),

    # Learning check for Pattern 4: Same dropdown, different selection
    # Lesson about verifying selection should transfer.
    BrowserTask(
        id="dropdown-select-option1",
        title="Select Option 1 from dropdown and verify",
        url="https://the-internet.herokuapp.com/dropdown",
        prompt=(
            "There is a dropdown on this page. "
            "Select 'Option 1' from the dropdown. "
            "After selecting, confirm what is selected and report "
            "the default option that was shown before you made a selection."
        ),
        max_steps=8,
        validation=TaskValidation(
            mode="data_extraction",
            data_extraction_schema={
                "type": "object",
                "properties": {
                    "selected_option": {
                        "type": "string",
                        "description": "The currently selected option after your action",
                    },
                    "default_text": {
                        "type": "string",
                        "description": "The default/placeholder text shown before any selection",
                    },
                },
            },
            expected_data={
                "selected_option": "Option 1",
                "default_text": "Please select an option",
            },
        ),
        tags=["dropdown", "selection", "defaults", "learning-check"],
    ),
]

# Learning pairs: (explorer_index, check_index, description)
LEARNING_PAIRS = [
    (0, 4, "Table Queries (highest due → lowest due)"),
    (1, 5, "Dynamic Loading (Example 1 → Example 2)"),
    (2, 6, "Checkbox States (toggle to target → verify defaults)"),
    (3, 7, "Dropdown (select Option 2 → select Option 1)"),
]
