"""RabbitMQ connection manager using aio-pika with robust reconnection and publisher confirms."""
import os
import inspect
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse
import aio_pika
from dotenv import load_dotenv
from app.config import settings

load_dotenv()
logger = logging.getLogger(__name__)


async def connect_rabbitmq(
    url: Optional[str] = None,
    timeout: Optional[int] = None
) -> Tuple[aio_pika.RobustConnection, aio_pika.RobustChannel]:
    """Establish an authenticated, robust connection and channel with publisher confirms.
    
    aio-pika supports asynchronous communication, connection recovery, and publisher confirms.
    """
    broker_url = url or os.environ.get("RABBITMQ_URL") or settings.rabbitmq_url
    timeout_secs = timeout or settings.rabbitmq_timeout_seconds

    connection = await aio_pika.connect_robust(
        broker_url,
        timeout=timeout_secs
    )
    channel_or_awaitable = connection.channel(
        publisher_confirms=True,
        on_return_raises=True
    )
    if inspect.isawaitable(channel_or_awaitable):
        channel = await channel_or_awaitable
    else:
        channel = channel_or_awaitable

    return connection, channel


class RabbitMQConnection:
    """Manages the application-lifetime RabbitMQ broker connection and channel.
    
    Keeps the connection open across the application's lifecycle, initialized
    during FastAPI startup and closed cleanly during shutdown.
    Avoids opening new broker connections for individual spoken commands.
    """

    def __init__(self, amqp_url: Optional[str] = None):
        self._custom_url = amqp_url
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self._is_connecting: bool = False

    @property
    def amqp_url(self) -> str:
        return self._custom_url or os.environ.get("RABBITMQ_URL") or settings.rabbitmq_url

    @property
    def is_connected(self) -> bool:
        return bool(
            self.connection
            and not self.connection.is_closed
            and self.channel
            and not self.channel.is_closed
        )

    def is_placeholder_url(self) -> bool:
        raw_url = (self.amqp_url or "").lower()
        placeholders = [
            "broker_host",
            "your-rabbitmq-host",
            "user:password@broker_host",
            "your-rabbitmq-user"
        ]
        return any(p in raw_url for p in placeholders)

    def sanitized_url(self) -> str:
        try:
            parsed = urlparse(self.amqp_url)
            netloc = parsed.hostname or "unknown"
            if parsed.port:
                netloc += f":{parsed.port}"
            return f"{parsed.scheme}://***:***@{netloc}{parsed.path}"
        except Exception:
            return "amqp://***:***@broker"

    async def connect(self) -> bool:
        """Establish or recover broker connection during application startup."""
        if self.is_connected:
            return True

        if self.is_placeholder_url():
            logger.info(
                f"RabbitMQ broker configured with placeholder URL ({self.sanitized_url()}). "
                "Operating with local mock transport until deployment broker credentials are provided."
            )
            return False

        try:
            self._is_connecting = True
            self.connection, self.channel = await connect_rabbitmq(
                self.amqp_url,
                timeout=settings.rabbitmq_timeout_seconds
            )
            logger.info(f"Established authenticated connection to RabbitMQ broker at {self.sanitized_url()}.")
            return True
        except Exception as e:
            logger.warning(
                f"RabbitMQ connection not established ({e}) for {self.sanitized_url()}. "
                "Commands will fallback to local transport until broker is reachable."
            )
            return False
        finally:
            self._is_connecting = False

    async def get_channel(self) -> Optional[aio_pika.RobustChannel]:
        """Return active channel or attempt reconnection."""
        if self.channel and not self.channel.is_closed:
            return self.channel
        if not self._is_connecting:
            await self.connect()
        return self.channel if (self.channel and not self.channel.is_closed) else None

    async def close(self):
        """Clean up channel and connection during application shutdown."""
        try:
            if self.channel and not self.channel.is_closed:
                await self.channel.close()
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
            logger.info("Closed RabbitMQ broker connection cleanly.")
        except Exception as e:
            logger.warning(f"Error while closing RabbitMQ connection: {e}")
        finally:
            self.channel = None
            self.connection = None


rabbitmq_connection = RabbitMQConnection()
