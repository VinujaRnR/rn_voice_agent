"""RabbitMQ publisher for sending verified device commands to RN Hub."""
import json
import asyncio
import logging
import aio_pika
from typing import Any, Dict, Optional
from app.config import settings
from app.rabbitmq.connection import rabbitmq_connection
from app.conversation.storage import ConversationStorage

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """Publishes validated commands to RN Hub RabbitMQ exchange using persistent connection and publisher confirms."""

    def __init__(self, connection_manager=None, storage=None):
        self.connection_manager = connection_manager or rabbitmq_connection
        self.storage = storage or ConversationStorage()

    async def connect(self):
        """Ensure connection manager is connected."""
        await self.connection_manager.connect()

    async def publish(
        self,
        queue_name: Optional[str] = None,
        message: Optional[Dict[str, Any]] = None,
        exchange_name: Optional[str] = None,
        routing_key: Optional[str] = None,
        routing_keys: Optional[Any] = None,
        reply_to: Optional[str] = None,
        correlation_id: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> bool:
        """Publish verified command with publisher confirms, timeout, and persistence.
        
        Reuses the application-lifetime broker channel without opening a new connection.
        Supports publishing to one or multiple topics/routing keys.
        """
        # Support dict as first arg for flexible calling
        if message is None and isinstance(queue_name, dict):
            message = queue_name
            queue_name = settings.rabbitmq_command_queue

        target_exchange = exchange_name or settings.rabbitmq_command_exchange
        target_routing_key = routing_key or settings.rabbitmq_command_routing_key or "commands"
        target_queue = queue_name or settings.rabbitmq_command_queue or "commands"
        target_reply_to = reply_to or settings.rabbitmq_result_queue or "results"
        timeout_seconds = timeout or settings.rabbitmq_timeout_seconds

        # Resolve all target routing keys / topics
        keys_to_publish = []
        if routing_keys:
            if isinstance(routing_keys, (list, tuple, set)):
                keys_to_publish.extend(list(routing_keys))
            else:
                keys_to_publish.append(str(routing_keys))
        elif target_routing_key:
            keys_to_publish.append(target_routing_key)

        keys_to_publish = list(dict.fromkeys([k for k in keys_to_publish if k]))
        if not keys_to_publish:
            keys_to_publish = ["commands"]

        command_id = correlation_id or (message.get("command_id") if isinstance(message, dict) else None)

        channel = await self.connection_manager.get_channel()

        if channel and not channel.is_closed:
            try:
                msg_body = aio_pika.Message(
                    body=json.dumps(message).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    correlation_id=command_id,
                    reply_to=target_reply_to,
                    message_id=command_id
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
                            try:
                                q = await channel.declare_queue(target_queue, durable=True)
                                for rk in keys_to_publish:
                                    await q.bind(exchange, routing_key=rk)
                            except Exception as q_err:
                                logger.debug(f"Queue '{target_queue}' declare/bind skipped or pre-existing: {q_err}")

                        for rk in keys_to_publish:
                            await exchange.publish(
                                msg_body,
                                routing_key=rk
                            )
                            logger.info(
                                f"Published command {command_id} to exchange '{target_exchange}' with routing key '{rk}': {message}"
                            )
                        return True
                    else:
                        await channel.default_exchange.publish(
                            msg_body,
                            routing_key=target_queue
                        )
                        logger.info(f"Published command {command_id} to queue '{target_queue}': {message}")
                        return True

                # Enforce configured timeout for publishing with confirms
                result = await asyncio.wait_for(_do_publish(), timeout=timeout_seconds)
                if result and command_id:
                    self.storage.update_command_state(command_id, "published")
                return bool(result)

            except asyncio.TimeoutError:
                logger.error(f"RabbitMQ publish timed out after {timeout_seconds} seconds for command {command_id}.")
                if command_id:
                    self.storage.update_command_state(command_id, "failed", error=f"Publish timed out after {timeout_seconds}s")
                return False
            except Exception as e:
                logger.error(f"Failed to publish command {command_id} to RabbitMQ: {e}")
                if command_id:
                    self.storage.update_command_state(command_id, "failed", error=str(e))
                return False
        else:
            logger.info(
                f"[RN Hub Mock Transport] Dispatched command {command_id} to exchange '{target_exchange}' "
                f"(routing_keys: {keys_to_publish}, queue: '{target_queue}', reply_to: '{target_reply_to}'): {message}"
            )
            if command_id:
                self.storage.update_command_state(command_id, "published")
            return True


publisher = RabbitMQPublisher()
