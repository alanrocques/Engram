"""Skyvern + Engram Live Demo — Wrapper Pattern for Browser Automation.

Runs real browser tasks through Skyvern with Engram's memory loop.
Tasks use the-internet.herokuapp.com for stable, predictable challenges.

Multiple rounds demonstrate score improvement as lessons are learned
from earlier attempts and retrieved for later ones.

Usage:
    cd integrations
    SKYVERN_API_KEY=... uv run python -m skyvern.scenarios.live_demo
    SKYVERN_API_KEY=... uv run python -m skyvern.scenarios.live_demo --seed --rounds 3

Prerequisites:
    - Running Engram backend (API + Celery + Postgres + Redis)
    - Running Skyvern instance (local Docker or cloud)
    - SKYVERN_API_KEY env var set
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

from skyvern.config import SkyvernConfig
from skyvern.tasks import TASK_LIST
from skyvern.wrapper import SkyvernEngramWrapper


def maybe_seed_lessons(config: SkyvernConfig, force_seed: bool = False) -> int:
    """Optionally seed lessons. Returns count of existing lessons."""
    from engram import EngramClient

    engram = EngramClient(base_url=config.engram_base_url, agent_id=config.agent_id)
    try:
        result = engram.retrieve(
            context="browser automation",
            domain=config.domain,
            top_k=1,
            min_confidence=0.0,
        )
        existing = result.total
        if existing > 0 and not force_seed:
            return existing
    except Exception:
        existing = 0
    finally:
        engram.close()

    if not force_seed:
        print("  Memory pool is empty -- starting cold (no seed lessons)")
        return 0

    print("  Seeding initial browser-automation lessons...")
    try:
        from skyvern.seed_lessons import seed

        created = seed(config.engram_base_url)
        count = len(created)
        if count > 0:
            print(f"  Seeded {count} lessons, waiting for embeddings...")
            time.sleep(5)
        return count
    except Exception as e:
        print(f"  Warning: Seeding failed ({e}), continuing without seed lessons")
        return 0


def run_demo(
    seed: bool = False,
    rounds: int = 3,
    skyvern_url: str | None = None,
    engram_url: str | None = None,
) -> None:
    """Run the full Skyvern + Engram live demo."""
    try:
        config = SkyvernConfig.from_env()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if skyvern_url:
        config.skyvern_base_url = skyvern_url
    if engram_url:
        config.engram_base_url = engram_url
    config.rounds = rounds

    print("=" * 60)
    print("  Skyvern + Engram Live Demo")
    print("  Wrapper Pattern for Browser Automation")
    print("=" * 60)

    mode = "with seed lessons" if seed else "cold start (no seeds)"
    print(f"\n  Engram:   {config.engram_base_url}")
    print(f"  Skyvern:  {config.skyvern_base_url}")
    print(f"  Agent:    {config.agent_id}")
    print(f"  Tasks:    {len(TASK_LIST)}")
    print(f"  Rounds:   {config.rounds}")
    print(f"  Mode:     {mode}")

    # Health checks
    print("\nHealth checks...")
    try:
        resp = httpx.get(f"{config.engram_base_url}/health", timeout=5.0)
        resp.raise_for_status()
        print("  Engram backend: healthy")
    except Exception as e:
        print(f"\n  ERROR: Engram backend not reachable at {config.engram_base_url}: {e}")
        print("  Make sure docker compose up -d and uvicorn are running.")
        sys.exit(1)

    try:
        resp = httpx.get(
            f"{config.skyvern_base_url}/api/v1/health",
            headers={"x-api-key": config.skyvern_api_key},
            timeout=10.0,
        )
        # Some Skyvern deployments return 200, others 404 for health
        # Accept any non-5xx as "reachable"
        if resp.status_code >= 500:
            raise httpx.HTTPStatusError(
                f"Skyvern returned {resp.status_code}",
                request=resp.request,
                response=resp,
            )
        print("  Skyvern: reachable")
    except Exception as e:
        print(f"\n  WARNING: Skyvern health check failed ({e})")
        print("  Continuing anyway — tasks will fail if Skyvern is not running.")

    # Seed if requested
    print("\nChecking memory pool...")
    existing = maybe_seed_lessons(config, force_seed=seed)
    print(f"  Lessons available: {existing}")

    # Run multi-round demo
    wrapper = SkyvernEngramWrapper(config)
    try:
        wrapper.run_multi_round(TASK_LIST, rounds=config.rounds)
    finally:
        wrapper.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skyvern + Engram Live Demo -- Wrapper Pattern for Browser Automation"
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed initial browser-automation lessons before running",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Number of rounds to run (default: 3)",
    )
    parser.add_argument(
        "--skyvern-url",
        type=str,
        default=None,
        help="Skyvern API base URL (default: from SKYVERN_BASE_URL env or http://localhost:8080)",
    )
    parser.add_argument(
        "--engram-url",
        type=str,
        default=None,
        help="Engram API base URL (default: from ENGRAM_BASE_URL env or http://localhost:8000)",
    )
    args = parser.parse_args()
    run_demo(
        seed=args.seed,
        rounds=args.rounds,
        skyvern_url=args.skyvern_url,
        engram_url=args.engram_url,
    )


if __name__ == "__main__":
    main()
