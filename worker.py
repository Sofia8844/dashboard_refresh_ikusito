from __future__ import annotations

import asyncio
import logging

from app.clients.canvas import CanvasClient
from app.clients.mcp import McpQueryClient
from app.config import get_settings
from app.database.session import get_sessionmaker
from app.messaging.rabbitmq import RabbitMQRefreshConsumer
from app.repositories.jobs import DashboardRefreshJobRepository
from app.services.worker import DashboardRefreshWorkerService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_refresh_message(payload: dict) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        service = DashboardRefreshWorkerService(
            settings=settings,
            repository=DashboardRefreshJobRepository(session),
            canvas_client=CanvasClient(settings),
            mcp_client=McpQueryClient(settings),
        )
        await service.process_message(payload)


async def main() -> None:
    settings = get_settings()
    logger.info("Starting dashboard refresh worker")
    await RabbitMQRefreshConsumer(settings).consume(handle_refresh_message)


if __name__ == "__main__":
    asyncio.run(main())
