"""RabbitMQ consumer for processing inbound robot events and RN Hub telemetry."""
import json
import logging
import aio_pika
from typing import Callable, Awaitable, Optional
from app.config import settings
from app.rabbitmq.connection import rabbitmq_connection

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """Consumes telemetry, status updates, and events from RN Hub queues."""

    def __init__(self, channel: Optional[aio_pika.abc.AbstractChannel] = None):
        self._channel = channel

    async def get_channel(self) -> Optional[aio_pika.abc.AbstractChannel]:
        if self._channel and not self._channel.is_closed:
            return self._channel
        return await rabbitmq_connection.get_channel()

    async def consume(
        self,
        queue_name: str,
        callback: Callable[[dict], Awaitable[None]],
        exchange_name: Optional[str] = None,
        routing_key: Optional[str] = None
    ):
        """Consume messages from a durable queue with automatic message acknowledgement."""
        channel = await self.get_channel()
        if not channel or channel.is_closed:
            logger.warning("RabbitMQ consumer cannot start: no active broker channel available.")
            return

        queue = await channel.declare_queue(queue_name, durable=True)

        if exchange_name:
            target_key = routing_key or "#"
            exchange = await channel.declare_exchange(
                exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            await queue.bind(exchange, routing_key=target_key)
            logger.info(f"Bound consumer queue '{queue_name}' to exchange '{exchange_name}' with key '{target_key}'.")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                        await callback(payload)
                    except Exception as e:
                        logger.error(f"Error processing inbound RabbitMQ message: {e}")
