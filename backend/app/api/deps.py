from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_async_session

AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
