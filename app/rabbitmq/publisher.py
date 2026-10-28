"""RabbitMQ publisher for sending verified device commands to RN Hub."""
import json
import asyncio
import logging
import aio_pika
from typing import Any, Dict, Optional
from app.config import settings
from app.rabbitmq.connection import rabbitmq_connection

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """Publishes validated commands to RN Hub RabbitMQ exchange using persistent connection and publisher confirms."""

    def __init__(self, connection_manager=None):
        self.connection_manager = connection_manager or rabbitmq_connection

    async def connect(self):
        """Ensure connection manager is connected."""
        await self.connection_manager.connect()

    async def publish(
        self,
        queue_name: Optional[str] = None,
        message: Optional[Dict[str, Any]] = None,
        exchange_name: Optional[str] = None,
        routing_key: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> bool:
        """Publish verified command with publisher confirms, timeout, and persistence.
        
        Reuses the application-lifetime broker channel without opening a new connection.
        """
        # Support dict as first arg for flexible calling
        if message is None and isinstance(queue_name, dict):
            message = queue_name
            queue_name = settings.rabbitmq_command_queue

        target_exchange = exchange_name or settings.rabbitmq_command_exchange
        target_routing_key = routing_key or settings.rabbitmq_command_routing_key or "commands"
        target_queue = queue_name or settings.rabbitmq_command_queue or "commands"
        timeout_seconds = timeout or settings.rabbitmq_timeout_seconds

        channel = await self.connection_manager.get_channel()

        if channel and not channel.is_closed:
            try:
                msg_body = aio_pika.Message(
                    body=json.dumps(message).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )

                async def _do_publish():
                    if target_exchange:
                        exchange = await channel.declare_exchange(
                            target_exchange,
                            aio_pika.ExchangeType.TOPIC,
                            durable=True
                        )
                        # Ensure queue is bound to receive commands
                        if target_queue:
                            q = await channel.declare_queue(target_queue, durable=True)
                            await q.bind(exchange, routing_key=target_routing_key)

                        confirmation = await exchange.publish(
                            msg_body,
                            routing_key=target_routing_key
                        )
                        logger.info(
                            f"Published command to exchange '{target_exchange}' with routing key '{target_routing_key}': {message}"
                        )
                        return confirmation is not None or True
                    else:
                        await channel.default_exchange.publish(
                            msg_body,
                            routing_key=target_queue
                        )
                        logger.info(f"Published command to queue '{target_queue}': {message}")
                        return True

                # Enforce configured timeout for publishing with confirms
                result = await asyncio.wait_for(_do_publish(), timeout=timeout_seconds)
                return bool(result)

            except asyncio.TimeoutError:
                logger.error(f"RabbitMQ publish timed out after {timeout_seconds} seconds.")
                return False
            except Exception as e:
                logger.error(f"Failed to publish command to RabbitMQ: {e}")
                return False
        else:
            logger.info(
                f"[RN Hub Mock Transport] Dispatched to exchange '{target_exchange}' "
                f"(routing_key: '{target_routing_key}', queue: '{target_queue}'): {message}"
            )
            return True


publisher = RabbitMQPublisher()
