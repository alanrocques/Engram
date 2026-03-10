"""Seed browser-automation lessons into Engram for cold start."""

import httpx

AGENT_ID = "skyvern-engram-v1"
DOMAIN = "browser-automation"

SEED_LESSONS = [
    {
        "agent_id": AGENT_ID,
        "task_context": "Interacting with a page that has a JavaScript alert, confirm, or prompt dialog",
        "action_taken": "Tried to click page elements while a JS dialog was blocking the page",
        "outcome": "failure",
        "lesson_text": (
            "JavaScript alert/confirm/prompt dialogs block ALL page interaction until dismissed. "
            "After clicking a button that triggers a JS dialog, you MUST handle the dialog "
            "(accept, dismiss, or enter text) before trying to read or click anything else on the page. "
            "For JS Prompt dialogs, you need to type text into the prompt input field before accepting. "
            "The result of the dialog action is usually shown in a #result element on the page."
        ),
        "tags": ["js-alerts", "dialogs", "blocking", "browser-automation"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Extracting content from elements inside iframes or nested iframes",
        "action_taken": "Used standard selectors to find text that was inside an iframe",
        "outcome": "failure",
        "lesson_text": (
            "Content inside iframes exists in a separate browsing context — standard page "
            "selectors cannot reach it. For nested iframes (e.g., a top frame containing "
            "left/middle/right sub-frames), you must switch into each frame level sequentially. "
            "WYSIWYG editors like TinyMCE also render content in an iframe. Always check if "
            "target content is inside an iframe before trying to extract it. Switch frame context "
            "first, then use selectors within that frame."
        ),
        "tags": ["iframes", "nested-frames", "context-switching", "browser-automation"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Multi-step workflow requiring login then extracting data from the post-login page",
        "action_taken": "Logged in but failed to extract flash message because it disappears quickly",
        "outcome": "partial",
        "lesson_text": (
            "After form submission (especially login), the resulting page may show temporary "
            "flash messages that disappear after a few seconds. Extract flash/notification text "
            "immediately after the page loads — don't perform other actions first. For multi-step "
            "tasks (login then extract), capture all data from the destination page in one step. "
            "Flash messages on the-internet.herokuapp.com have a close button (x) appended to "
            "the text — strip it when extracting."
        ),
        "tags": ["multi-step", "flash-messages", "login", "browser-automation"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Sorting a table by clicking column headers and extracting sorted data",
        "action_taken": "Extracted data before sorting, getting wrong results",
        "outcome": "failure",
        "lesson_text": (
            "When tasked with sorting a table and extracting data, you must: (1) click the "
            "correct column header to trigger sorting, (2) verify the sort direction (ascending "
            "vs descending — you may need to click twice for descending), (3) wait for the DOM "
            "to update after the sort, (4) THEN extract data. On the-internet.herokuapp.com/tables, "
            "the second table (Example 2) has clickable column headers. Note that sorting by "
            "'Due' requires understanding dollar amounts, not alphabetical order."
        ),
        "tags": ["tables", "sorting", "data-extraction", "browser-automation"],
        "domain": DOMAIN,
    },
]


def seed(base_url: str = "http://localhost:8000") -> list[str]:
    """
    Seed initial browser-automation lessons into Engram.

    Args:
        base_url: Engram API base URL.

    Returns:
        List of created lesson IDs.
    """
    client = httpx.Client(
        base_url=f"{base_url.rstrip('/')}/api/v1",
        timeout=30.0,
        headers={"Content-Type": "application/json"},
    )
    created_ids: list[str] = []
    try:
        for lesson in SEED_LESSONS:
            response = client.post("/lessons", json=lesson)
            response.raise_for_status()
            data = response.json()
            created_ids.append(data["id"])
            print(f"  Seeded lesson: {data['id']} -- {lesson['tags'][0]}")
        print(f"\nSeeded {len(created_ids)} lessons successfully.")
        return created_ids
    finally:
        client.close()


if __name__ == "__main__":
    import os

    url = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
    print(f"Seeding Skyvern browser-automation lessons into Engram at {url}...")
    seed(url)
