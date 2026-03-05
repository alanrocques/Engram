"""
LangChain/LangGraph middleware hooks for automatic instrumentation.

This module provides middleware for popular agent frameworks to automatically:
- Capture execution traces
- Retrieve relevant lessons before decisions
- Report outcomes after execution

TODO: Implement in Phase 4
"""


class LangChainMiddleware:
    """Middleware for LangChain agents."""

    def __init__(self, client):
        self.client = client

    # TODO: Implement LangChain callback handlers


class LangGraphMiddleware:
    """Middleware for LangGraph agents."""

    def __init__(self, client):
        self.client = client

    # TODO: Implement LangGraph instrumentation
