from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.config import Settings


class RefreshJobPublisher(Protocol):
    async def publish_refresh_job(self, payload: dict[str, str]) -> None:
        ...


class RabbitMQRefreshPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def publish_refresh_job(self, payload: dict[str, str]) -> None:
        connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            exchange = await _declare_topology(channel, self.settings)
            message = aio_pika.Message(
                json.dumps(payload).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-retry-count": 0},
            )
            await exchange.publish(message, routing_key=self.settings.rabbitmq_routing_key)


class RabbitMQRefreshConsumer:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def consume(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=self.settings.rabbitmq_prefetch_count)
        exchange = await _declare_topology(channel, self.settings)
        queue = await channel.get_queue(self.settings.rabbitmq_queue)

        async with connection, queue.iterator() as iterator:
            async for message in iterator:
                await self._handle_message(message, handler, exchange)

    async def _handle_message(
        self,
        message: AbstractIncomingMessage,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        exchange: aio_pika.Exchange,
    ) -> None:
        try:
            payload = json.loads(message.body.decode("utf-8"))
            await handler(payload)
        except Exception:
            retry_count = int((message.headers or {}).get("x-retry-count", 0))
            if retry_count >= self.settings.rabbitmq_max_retries:
                await message.reject(requeue=False)
            else:
                retry_message = aio_pika.Message(
                    message.body,
                    content_type=message.content_type,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers={**(message.headers or {}), "x-retry-count": retry_count + 1},
                )
                await exchange.publish(retry_message, routing_key=self.settings.rabbitmq_routing_key)
                await message.ack()
            raise
        else:
            await message.ack()


async def _declare_topology(channel: aio_pika.Channel, settings: Settings) -> aio_pika.Exchange:
    dlx = await channel.declare_exchange(settings.rabbitmq_dlx, aio_pika.ExchangeType.DIRECT, durable=True)
    await channel.declare_queue(settings.rabbitmq_dlq, durable=True)
    queue = await channel.declare_queue(
        settings.rabbitmq_queue,
        durable=True,
        arguments={"x-dead-letter-exchange": settings.rabbitmq_dlx},
    )
    await queue.bind(dlx, routing_key=settings.rabbitmq_queue)
    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await queue.bind(exchange, routing_key=settings.rabbitmq_routing_key)
    return exchange
