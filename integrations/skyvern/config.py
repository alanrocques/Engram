"""Configuration for Skyvern + Engram integration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SkyvernConfig:
    """Configuration for the Skyvern-Engram wrapper."""

    skyvern_api_key: str
    skyvern_base_url: str = "http://localhost:8080"
    engram_base_url: str = "http://localhost:8000"
    agent_id: str = "skyvern-engram-v1"
    domain: str = "browser-automation"
    rounds: int = 3
    task_delay_seconds: float = 5.0
    round_delay_seconds: float = 10.0
    skyvern_poll_interval: float = 5.0
    skyvern_poll_timeout: float = 300.0

    @classmethod
    def from_env(cls) -> SkyvernConfig:
        """Load configuration from environment variables."""
        api_key = os.environ.get("SKYVERN_API_KEY", "")
        if not api_key:
            raise ValueError("SKYVERN_API_KEY environment variable is required")
        return cls(
            skyvern_api_key=api_key,
            skyvern_base_url=os.environ.get("SKYVERN_BASE_URL", "http://localhost:8080"),
            engram_base_url=os.environ.get("ENGRAM_BASE_URL", "http://localhost:8000"),
            agent_id=os.environ.get("SKYVERN_AGENT_ID", "skyvern-engram-v1"),
            rounds=int(os.environ.get("SKYVERN_ROUNDS", "3")),
        )
