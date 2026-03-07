"""Seed initial test-automation lessons into Engram for cold start."""

import httpx

AGENT_ID = "hercules-test-v1"
DOMAIN = "test-automation"

SEED_LESSONS = [
    {
        "agent_id": AGENT_ID,
        "task_context": "Selecting elements on pages with dynamically generated IDs",
        "action_taken": "Used CSS ID selectors like #add-to-cart-btn on a React SPA",
        "outcome": "failure",
        "lesson_text": (
            "Avoid hardcoded CSS ID selectors on React/Vue/Angular SPAs. "
            "Frameworks like React's useId() generate non-deterministic IDs that change "
            "across renders. Prefer data-testid attributes, aria-labels, or role-based "
            "selectors (e.g., [role='button'][aria-label='Add to cart']) for stable element targeting."
        ),
        "tags": ["selectors", "dynamic-content", "react", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Waiting for page navigation after triggering an action",
        "action_taken": "Used a fixed timeout of 10 seconds for all navigation waits",
        "outcome": "failure",
        "lesson_text": (
            "Fixed navigation timeouts are fragile. Payment processing, SSO redirects, "
            "and report generation can exceed default timeouts on staging environments. "
            "Use adaptive wait strategies: wait for specific URL patterns, network idle, "
            "or DOM element appearance rather than fixed timeouts. Set generous timeouts "
            "(30s+) for operations known to be slow on staging."
        ),
        "tags": ["timeouts", "navigation", "waits", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Interacting with elements inside iframes (payment forms, embedded widgets)",
        "action_taken": "Attempted to use standard selectors to find elements inside an iframe",
        "outcome": "failure",
        "lesson_text": (
            "Elements inside iframes (especially payment forms like Stripe, Braintree) "
            "are in a separate browsing context. Standard selectors won't find them. "
            "Use frame_locator('iframe[src*=\"stripe\"]') or page.frame() to switch context "
            "before interacting with iframe content. Always switch back to the main frame afterward."
        ),
        "tags": ["iframes", "payment-forms", "context-switching", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Verifying UI state immediately after triggering an async action",
        "action_taken": "Asserted element text immediately after clicking an action button",
        "outcome": "failure",
        "lesson_text": (
            "Modern SPAs update UI asynchronously. Asserting state immediately after "
            "triggering an action (add to cart, apply filter, submit form) will read "
            "stale DOM values. Wait for the specific state change: use waitForSelector "
            "with text content, poll for text changes, or wait for the relevant network "
            "request to complete before asserting."
        ),
        "tags": ["assertions", "async", "race-conditions", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Uploading files via native OS file dialogs",
        "action_taken": "Clicked the upload button which triggered a native OS file dialog",
        "outcome": "failure",
        "lesson_text": (
            "Native OS file dialogs cannot be automated with browser selectors. "
            "Instead of clicking the visible upload button, locate the hidden "
            "<input type='file'> element and use set_input_files() or setInputFiles() "
            "to programmatically set the file. Most upload UIs have a hidden file input "
            "that the visible button triggers."
        ),
        "tags": ["file-upload", "native-dialogs", "workaround", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Handling OAuth popup windows during login tests",
        "action_taken": "Waited for a popup window that was blocked by browser settings",
        "outcome": "failure",
        "lesson_text": (
            "Headless browsers block popups by default. For OAuth flows that open popups, "
            "configure the browser context to allow popups, or intercept the OAuth redirect "
            "URL directly. In Playwright, listen for the 'popup' event on the page before "
            "clicking the OAuth button. Alternatively, test OAuth via API token injection "
            "to bypass the popup flow entirely."
        ),
        "tags": ["oauth", "popups", "authentication", "best-practice"],
        "domain": DOMAIN,
    },
    {
        "agent_id": AGENT_ID,
        "task_context": "Interacting with elements inside Shadow DOM (web components)",
        "action_taken": "Used standard CSS selectors to find elements inside a shadow root",
        "outcome": "failure",
        "lesson_text": (
            "Web components with Shadow DOM encapsulate their internal elements. "
            "Standard selectors cannot pierce the shadow boundary. Use "
            "page.locator('host-element').locator('internal-selector') in Playwright, "
            "or element.shadowRoot.querySelector() in raw JS. Check if the shadow root "
            "mode is 'open' (accessible) or 'closed' (requires workaround)."
        ),
        "tags": ["shadow-dom", "web-components", "selectors", "best-practice"],
        "domain": DOMAIN,
    },
]


def seed(base_url: str = "http://localhost:8000") -> list[str]:
    """
    Seed initial lessons into Engram and return their IDs.

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
            print(f"  Seeded lesson: {data['id']} — {lesson['tags'][0]}")
        print(f"\nSeeded {len(created_ids)} lessons successfully.")
        return created_ids
    finally:
        client.close()


if __name__ == "__main__":
    import os

    url = os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000")
    print(f"Seeding Hercules lessons into Engram at {url}...")
    seed(url)
