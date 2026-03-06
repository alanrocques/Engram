import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import AsyncSessionDep
from app.config import settings
from app.main import app


@pytest.fixture
async def client():
    """
    Async HTTP client for testing the FastAPI app.

    Uses NullPool on the test engine so each test gets a fresh connection that
    isn't bound to any event loop, avoiding "Future attached to a different
    loop" errors when tests share a module-level engine singleton.
    """
    test_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def override_get_session():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[AsyncSessionDep.__class__] = override_get_session

    # FastAPI dependency overrides key on the actual dependency callable
    from app.db.engine import get_async_session
    app.dependency_overrides[get_async_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    await test_engine.dispose()
