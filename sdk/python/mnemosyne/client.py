from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel


class RetrievedLesson(BaseModel):
    """A lesson retrieved from Mnemosyne."""

    id: str
    agent_id: str
    task_context: str
    action_taken: str
    outcome: str
    lesson_text: str
    confidence: float
    tags: list[str]
    domain: str
    similarity: float


class RetrieveResult(BaseModel):
    """Result of a retrieval request."""

    lessons: list[RetrievedLesson]
    context: str | None
    total: int


class TraceResult(BaseModel):
    """Result of a trace ingestion."""

    id: str
    agent_id: str
    status: str


class LessonResult(BaseModel):
    """Result of a lesson creation."""

    id: str
    agent_id: str
    task_context: str
    lesson_text: str
    outcome: str
    confidence: float


class MnemosyneClient:
    """
    Synchronous client for Mnemosyne API.

    Example:
        client = MnemosyneClient(base_url="http://localhost:8000", agent_id="my-agent")
        lessons = client.retrieve("How do I handle refunds?")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            timeout=timeout,
            headers=self._get_headers(),
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def retrieve(
        self,
        context: str,
        agent_id: str | None = None,
        domain: str | None = None,
        top_k: int = 5,
        min_confidence: float = 0.3,
        include_context: bool = True,
    ) -> RetrieveResult:
        """
        Retrieve lessons relevant to the given context.

        Args:
            context: The situation or query to find relevant lessons for
            agent_id: Filter by agent ID (defaults to client's agent_id)
            domain: Filter by domain
            top_k: Maximum number of lessons to return
            min_confidence: Minimum confidence threshold
            include_context: Include formatted context string for prompts

        Returns:
            RetrieveResult with lessons and optional formatted context
        """
        response = self._client.post(
            "/retrieve",
            json={
                "query": context,
                "agent_id": agent_id or self.agent_id,
                "domain": domain,
                "top_k": top_k,
                "min_confidence": min_confidence,
                "include_context": include_context,
            },
        )
        response.raise_for_status()
        return RetrieveResult(**response.json())

    def ingest_trace(
        self,
        trace_data: dict[str, Any],
        agent_id: str | None = None,
        process_async: bool = True,
    ) -> TraceResult:
        """
        Ingest an agent execution trace.

        Args:
            trace_data: The trace data to ingest
            agent_id: Agent ID (defaults to client's agent_id)
            process_async: Queue for background processing

        Returns:
            TraceResult with trace ID and status
        """
        response = self._client.post(
            "/traces",
            params={"process_async": process_async},
            json={
                "agent_id": agent_id or self.agent_id or "unknown",
                "trace_data": trace_data,
                "span_count": len(trace_data.get("spans", [])),
            },
        )
        response.raise_for_status()
        data = response.json()
        return TraceResult(id=str(data["id"]), agent_id=data["agent_id"], status=data["status"])

    def create_lesson(
        self,
        task_context: str,
        action_taken: str,
        outcome: str,
        lesson_text: str,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        domain: str = "general",
    ) -> LessonResult:
        """
        Create a lesson directly (without going through trace extraction).

        Args:
            task_context: What the agent was trying to do
            action_taken: What action was taken
            outcome: "success", "failure", or "partial"
            lesson_text: The distilled takeaway
            agent_id: Agent ID (defaults to client's agent_id)
            tags: Category tags
            domain: Domain category

        Returns:
            LessonResult with lesson ID
        """
        response = self._client.post(
            "/lessons",
            json={
                "agent_id": agent_id or self.agent_id or "unknown",
                "task_context": task_context,
                "action_taken": action_taken,
                "outcome": outcome,
                "lesson_text": lesson_text,
                "tags": tags or [],
                "domain": domain,
            },
        )
        response.raise_for_status()
        data = response.json()
        return LessonResult(
            id=str(data["id"]),
            agent_id=data["agent_id"],
            task_context=data["task_context"],
            lesson_text=data["lesson_text"],
            outcome=data["outcome"],
            confidence=data["confidence"],
        )

    def report_outcome(
        self,
        trace_id: str,
        outcome: str,
    ) -> None:
        """
        Report the outcome of a previously ingested trace.
        Triggers reprocessing to update the associated lesson.

        Args:
            trace_id: The trace ID to update
            outcome: The outcome ("success", "failure", "partial")
        """
        response = self._client.post(f"/traces/{trace_id}/process")
        response.raise_for_status()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncMnemosyneClient:
    """
    Asynchronous client for Mnemosyne API.

    Example:
        async with AsyncMnemosyneClient(base_url="http://localhost:8000") as client:
            lessons = await client.retrieve("How do I handle refunds?")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1",
            timeout=timeout,
            headers=self._get_headers(),
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def retrieve(
        self,
        context: str,
        agent_id: str | None = None,
        domain: str | None = None,
        top_k: int = 5,
        min_confidence: float = 0.3,
        include_context: bool = True,
    ) -> RetrieveResult:
        """Retrieve lessons relevant to the given context."""
        response = await self._client.post(
            "/retrieve",
            json={
                "query": context,
                "agent_id": agent_id or self.agent_id,
                "domain": domain,
                "top_k": top_k,
                "min_confidence": min_confidence,
                "include_context": include_context,
            },
        )
        response.raise_for_status()
        return RetrieveResult(**response.json())

    async def ingest_trace(
        self,
        trace_data: dict[str, Any],
        agent_id: str | None = None,
        process_async: bool = True,
    ) -> TraceResult:
        """Ingest an agent execution trace."""
        response = await self._client.post(
            "/traces",
            params={"process_async": process_async},
            json={
                "agent_id": agent_id or self.agent_id or "unknown",
                "trace_data": trace_data,
                "span_count": len(trace_data.get("spans", [])),
            },
        )
        response.raise_for_status()
        data = response.json()
        return TraceResult(id=str(data["id"]), agent_id=data["agent_id"], status=data["status"])

    async def create_lesson(
        self,
        task_context: str,
        action_taken: str,
        outcome: str,
        lesson_text: str,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        domain: str = "general",
    ) -> LessonResult:
        """Create a lesson directly."""
        response = await self._client.post(
            "/lessons",
            json={
                "agent_id": agent_id or self.agent_id or "unknown",
                "task_context": task_context,
                "action_taken": action_taken,
                "outcome": outcome,
                "lesson_text": lesson_text,
                "tags": tags or [],
                "domain": domain,
            },
        )
        response.raise_for_status()
        data = response.json()
        return LessonResult(
            id=str(data["id"]),
            agent_id=data["agent_id"],
            task_context=data["task_context"],
            lesson_text=data["lesson_text"],
            outcome=data["outcome"],
            confidence=data["confidence"],
        )

    async def report_outcome(self, trace_id: str, outcome: str) -> None:
        """Report the outcome of a previously ingested trace."""
        response = await self._client.post(f"/traces/{trace_id}/process")
        response.raise_for_status()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
