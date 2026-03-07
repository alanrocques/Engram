from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config() -> dict:
    return {
        "extraction_model": settings.extraction_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "lesson_confidence_half_life_days": settings.lesson_confidence_half_life_days,
        "max_lessons_per_retrieval": settings.max_lessons_per_retrieval,
        "min_confidence_threshold": settings.min_confidence_threshold,
        "otel_grpc_port": settings.otel_grpc_port,
        "otel_http_port": settings.otel_http_port,
    }
