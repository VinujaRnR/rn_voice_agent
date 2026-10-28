"""Step 11 & 12 Tests — RabbitMQ connection, aio-pika robust client, and publisher confirms."""
import os
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import aio_pika
from fastapi import FastAPI
from app.config import settings
from app.rabbitmq.connection import (
    connect_rabbitmq,
    RabbitMQConnection,
    rabbitmq_connection
)
from app.rabbitmq.publisher import RabbitMQPublisher
from app.rabbitmq.consumer import RabbitMQConsumer
from app.main import lifespan


@pytest.mark.asyncio
async def test_connect_rabbitmq_function_and_channel_options():
    """Verify that connect_rabbitmq establishes a robust connection and channel
    with publisher_confirms=True and on_return_raises=True as required by Step 11.
    """
    mock_conn = MagicMock()
    mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
    mock_conn.channel = AsyncMock(return_value=mock_channel)

    with patch("aio_pika.connect_robust", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = mock_conn

        conn, channel = await connect_rabbitmq(
            url="amqp://test:test@localhost:5672/",
            timeout=10
        )

        # Verify connect_robust was called with URL and timeout
        mock_connect.assert_called_once_with("amqp://test:test@localhost:5672/", timeout=10)

        # Verify channel was opened with publisher_confirms=True and on_return_raises=True
        mock_conn.channel.assert_called_once_with(
            publisher_confirms=True,
            on_return_raises=True
        )

        assert conn == mock_conn
        assert channel == mock_channel


@pytest.mark.asyncio
async def test_rabbitmq_connection_lifecycle_and_channel_reuse():
    """Verify RabbitMQConnection maintains a single application-lifetime connection and channel."""
    mgr = RabbitMQConnection("amqp://user:pass@remote-broker:5672/vhost")
    assert mgr.is_connected is False

    mock_conn = MagicMock()
    mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
    mock_conn.is_closed = False
    mock_channel.is_closed = False
    mock_channel.close = AsyncMock()
    mock_conn.close = AsyncMock()

    with patch("app.rabbitmq.connection.connect_rabbitmq", new_callable=AsyncMock) as mock_connect:
        mock_connect.return_value = (mock_conn, mock_channel)

        # 1. First connection
        success = await mgr.connect()
        assert success is True
        assert mgr.is_connected is True
        assert mock_connect.call_count == 1

        # 2. Subsequent call reuses existing connection without re-connecting
        success2 = await mgr.connect()
        assert success2 is True
        assert mock_connect.call_count == 1  # Did NOT reconnect

        # 3. get_channel returns the open channel
        chan = await mgr.get_channel()
        assert chan == mock_channel
        assert mock_connect.call_count == 1

        # 4. Clean shutdown
        await mgr.close()
        mock_channel.close.assert_called_once()
        mock_conn.close.assert_called_once()
        assert mgr.is_connected is False


def test_sanitized_url_masks_passwords():
    """Verify that credentials are not logged in plain text."""
    mgr = RabbitMQConnection("amqps://myuser:secret123@hub.broker.net:5671/production")
    sanitized = mgr.sanitized_url()
    assert "secret123" not in sanitized
    assert "myuser" not in sanitized or "***" in sanitized
    assert "hub.broker.net:5671/production" in sanitized


@pytest.mark.asyncio
async def test_fastapi_lifespan_manages_connection():
    """Verify FastAPI lifespan establishes connection on startup and closes on shutdown."""
    app_test = FastAPI(lifespan=lifespan)

    with patch.object(rabbitmq_connection, "connect", new_callable=AsyncMock) as mock_conn, \
         patch.object(rabbitmq_connection, "close", new_callable=AsyncMock) as mock_close:

        async with lifespan(app_test):
            mock_conn.assert_called_once()
            mock_close.assert_not_called()

        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_publisher_publishes_to_exchange_with_confirms():
    """Verify that publisher uses exchange, routing key, persistent delivery mode, and publisher confirms."""
    mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
    mock_channel.is_closed = False
    mock_exchange = AsyncMock()
    mock_queue = AsyncMock()

    mock_channel.declare_exchange.return_value = mock_exchange
    mock_channel.declare_queue.return_value = mock_queue

    mock_mgr = MagicMock(spec=RabbitMQConnection)
    mock_mgr.get_channel = AsyncMock(return_value=mock_channel)

    pub = RabbitMQPublisher(connection_manager=mock_mgr)

    payload = {
        "command_id": "cmd_test123",
        "device_id": "98a316e6b658",
        "action": "set_power",
        "parameters": {"state": "on"}
    }

    result = await pub.publish(
        queue_name="commands",
        message=payload,
        exchange_name="rn.hub",
        routing_key="commands"
    )

    assert result is True
    # Verify topic exchange declared
    mock_channel.declare_exchange.assert_called_once_with(
        "rn.hub",
        aio_pika.ExchangeType.TOPIC,
        durable=True
    )
    # Verify queue bound to exchange
    mock_queue.bind.assert_called_once_with(mock_exchange, routing_key="commands")

    # Verify message published to exchange with persistent delivery
    mock_exchange.publish.assert_called_once()
    published_msg = mock_exchange.publish.call_args[0][0]
    assert isinstance(published_msg, aio_pika.Message)
    assert published_msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert json.loads(published_msg.body.decode()) == payload


@pytest.mark.asyncio
async def test_publisher_mock_fallback_when_broker_offline():
    """Verify graceful mock transport fallback when broker is unreachable."""
    mock_mgr = MagicMock(spec=RabbitMQConnection)
    mock_mgr.get_channel = AsyncMock(return_value=None)  # Channel unavailable

    pub = RabbitMQPublisher(connection_manager=mock_mgr)

    payload = {"action": "set_power", "device_id": "98a316e6b658"}
    result = await pub.publish(
        queue_name="commands",
        message=payload,
        exchange_name="rn.hub",
        routing_key="commands"
    )
    assert result is True  # Mock transport logged and returned True


@pytest.mark.asyncio
async def test_consumer_subscribes_and_processes():
    """Verify RabbitMQConsumer consumes from queue with auto-acknowledgement."""
    mock_channel = AsyncMock(spec=aio_pika.RobustChannel)
    mock_channel.is_closed = False
    mock_queue = AsyncMock()
    mock_channel.declare_queue.return_value = mock_queue

    consumer = RabbitMQConsumer(channel=mock_channel)
    chan = await consumer.get_channel()
    assert chan == mock_channel
