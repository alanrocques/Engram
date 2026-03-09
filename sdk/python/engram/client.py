from typing import Any

import httpx
from pydantic import BaseModel


class RetrievedLesson(BaseModel):
    """A lesson retrieved from Engram."""

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
    utility: float = 0.5
    vector_score: float = 0.0
    keyword_score: float = 0.0
    has_conflict: bool = False
    conflict_ids: list[str] = []


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


class OutcomeResult(BaseModel):
    """Result of reporting a trace outcome."""

    trace_id: str
    outcome: str
    updated_lesson_ids: list[str]
    updated_count: int


class EngramClient:
    """
    Synchronous client for Engram API.

    Example:
        client = EngramClient(base_url="http://localhost:8000", agent_id="my-agent")
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
        search_mode: str | None = None,
        vector_weight: float | None = None,
        utility_weight: float | None = None,
        include_archived: bool = False,
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
            search_mode: Search mode: "vector", "keyword", or "hybrid" (default: backend default)
            vector_weight: Weight for vector score in hybrid mode (0.0-1.0)
            utility_weight: Weight for utility score in re-ranking (0.0-1.0)
            include_archived: Include archived lessons in results

        Returns:
            RetrieveResult with lessons and optional formatted context
        """
        payload: dict[str, Any] = {
            "query": context,
            "agent_id": agent_id or self.agent_id,
            "domain": domain,
            "top_k": top_k,
            "min_confidence": min_confidence,
            "include_context": include_context,
            "include_archived": include_archived,
        }
        if search_mode is not None:
            payload["search_mode"] = search_mode
        if vector_weight is not None:
            payload["vector_weight"] = vector_weight
        if utility_weight is not None:
            payload["utility_weight"] = utility_weight
        response = self._client.post("/retrieve", json=payload)
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
        retrieved_lesson_ids: list[str] | None = None,
        downstream_utility: float = 0.0,
        context_similarity: float = 1.0,
    ) -> OutcomeResult:
        """
        Report the outcome of a previously ingested trace.

        Triggers Bellman utility updates and failure penalty propagation
        for any lessons that were retrieved during this trace's execution.

        Args:
            trace_id: The trace ID to report on
            outcome: The outcome ("success", "failure", "partial")
            retrieved_lesson_ids: IDs of lessons that were in context when the trace ran
            downstream_utility: How useful the retrieved lessons were (0.0-1.0)
            context_similarity: Similarity score used when retrieving these lessons (0.0-1.0)

        Returns:
            OutcomeResult with updated lesson info
        """
        response = self._client.post(
            "/outcomes",
            json={
                "trace_id": trace_id,
                "outcome": outcome,
                "retrieved_lesson_ids": retrieved_lesson_ids or [],
                "downstream_utility": downstream_utility,
                "context_similarity": context_similarity,
            },
        )
        response.raise_for_status()
        return OutcomeResult(**response.json())

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class AsyncEngramClient:
    """
    Asynchronous client for Engram API.

    Example:
        async with AsyncEngramClient(base_url="http://localhost:8000") as client:
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
        search_mode: str | None = None,
        vector_weight: float | None = None,
        utility_weight: float | None = None,
        include_archived: bool = False,
    ) -> RetrieveResult:
        """Retrieve lessons relevant to the given context."""
        payload: dict[str, Any] = {
            "query": context,
            "agent_id": agent_id or self.agent_id,
            "domain": domain,
            "top_k": top_k,
            "min_confidence": min_confidence,
            "include_context": include_context,
            "include_archived": include_archived,
        }
        if search_mode is not None:
            payload["search_mode"] = search_mode
        if vector_weight is not None:
            payload["vector_weight"] = vector_weight
        if utility_weight is not None:
            payload["utility_weight"] = utility_weight
        response = await self._client.post("/retrieve", json=payload)
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

    async def report_outcome(
        self,
        trace_id: str,
        outcome: str,
        retrieved_lesson_ids: list[str] | None = None,
        downstream_utility: float = 0.0,
        context_similarity: float = 1.0,
    ) -> OutcomeResult:
        """
        Report the outcome of a previously ingested trace.

        Triggers Bellman utility updates and failure penalty propagation.
        """
        response = await self._client.post(
            "/outcomes",
            json={
                "trace_id": trace_id,
                "outcome": outcome,
                "retrieved_lesson_ids": retrieved_lesson_ids or [],
                "downstream_utility": downstream_utility,
                "context_similarity": context_similarity,
            },
        )
        response.raise_for_status()
        return OutcomeResult(**response.json())

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
