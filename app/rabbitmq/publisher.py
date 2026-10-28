"""RabbitMQ publisher for sending verified device commands to RN Hub."""
import json
import logging
import aio_pika
from typing import Any, Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    def __init__(self, amqp_url: Optional[str] = None):
        self.amqp_url = amqp_url or settings.rabbitmq_url
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None

    async def connect(self):
        try:
            self.connection = await aio_pika.connect_robust(self.amqp_url)
            self.channel = await self.connection.channel()
            logger.info("Connected to RabbitMQ for RN Hub command dispatch.")
        except Exception as e:
            logger.warning(f"RabbitMQ connection not established ({e}). Commands will log locally.")

    async def publish(
        self,
        queue_name: str = "rn_hub_commands",
        message: Optional[Dict[str, Any]] = None,
        exchange_name: Optional[str] = None,
        routing_key: Optional[str] = None
    ) -> bool:
        """Publish message to RabbitMQ exchange or queue with local mock fallback."""
        if message is None and isinstance(queue_name, dict):
            message = queue_name
            queue_name = settings.rabbitmq_command_queue or "rn_hub_commands"

        target_queue = queue_name or settings.rabbitmq_command_queue or "rn_hub_commands"
        target_routing_key = routing_key or settings.rabbitmq_command_routing_key or target_queue
        target_exchange = exchange_name or settings.rabbitmq_command_exchange

        if not self.channel or self.channel.is_closed:
            await self.connect()

        if self.channel and not self.channel.is_closed:
            try:
                msg_body = aio_pika.Message(
                    body=json.dumps(message).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                )
                if target_exchange:
                    try:
                        exchange = await self.channel.declare_exchange(
                            target_exchange,
                            aio_pika.ExchangeType.TOPIC,
                            durable=True
                        )
                        await exchange.publish(msg_body, routing_key=target_routing_key)
                        logger.info(f"Published command to exchange '{target_exchange}' with routing key '{target_routing_key}': {message}")
                        return True
                    except Exception as exc:
                        logger.warning(f"Failed to publish to custom exchange '{target_exchange}', falling back to default exchange: {exc}")

                await self.channel.default_exchange.publish(
                    msg_body,
                    routing_key=target_queue,
                )
                logger.info(f"Published command to {target_queue}: {message}")
                return True
            except Exception as e:
                logger.error(f"Failed to publish to RabbitMQ: {e}")
                return False
        else:
            logger.info(f"[RN Hub Mock Transport] Dispatched to {target_queue} (exchange: {target_exchange}, routing_key: {target_routing_key}): {message}")
            return True


publisher = RabbitMQPublisher()
