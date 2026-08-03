from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database.session import get_session
from app.messaging.rabbitmq import RabbitMQRefreshPublisher
from app.repositories.jobs import DashboardRefreshJobRepository
from app.services.refresh_jobs import RefreshJobService


async def get_refresh_job_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[RefreshJobService]:
    settings = get_settings()
    yield RefreshJobService(
        DashboardRefreshJobRepository(session),
        RabbitMQRefreshPublisher(settings),
    )
