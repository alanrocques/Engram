from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://mnemosyne:password@localhost:5432/mnemosyne"
    redis_url: str = "redis://localhost:6379/0"

    # LLM (for lesson extraction)
    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-5-20250929"

    # Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    otel_grpc_port: int = 4317
    otel_http_port: int = 4318

    # Auth
    api_key_secret: str = "change-me-in-production"

    # Curation
    lesson_confidence_half_life_days: int = 30
    max_lessons_per_retrieval: int = 10
    min_confidence_threshold: float = 0.3


settings = Settings()
