"""RabbitMQ consumer for processing inbound robot events, telemetry, and RN Hub execution results."""
import json
import asyncio
import logging
import aio_pika
from typing import Callable, Awaitable, Optional, Dict, Any
from app.config import settings
from app.rabbitmq.connection import rabbitmq_connection
from app.conversation.storage import ConversationStorage
from app.commands.lifecycle import CommandState, generate_speech_outcome, command_tracker
from app.commands.device_registry import device_registry

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


class CommandResultConsumer:
    """Consumes device execution results published by RN Hub and associates them with command lifecycle in SQLite.
    
    Implements Step 12 command lifecycle:
    validated -> published -> accepted -> completed
    Also handles: rejected, failed, expired, unknown.
    """

    def __init__(
        self,
        channel: Optional[aio_pika.abc.AbstractChannel] = None,
        storage: Optional[ConversationStorage] = None
    ):
        self._channel = channel
        self.storage = storage or ConversationStorage()
        self.is_running = False
        self._consume_task: Optional[asyncio.Task] = None

    async def get_channel(self) -> Optional[aio_pika.abc.AbstractChannel]:
        if self._channel and not self._channel.is_closed:
            return self._channel
        if rabbitmq_connection.channel and not rabbitmq_connection.channel.is_closed:
            return rabbitmq_connection.channel
        return None

    def process_result_payload(
        self,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process an execution result dictionary, update SQLite, and format speech outcome."""
        command_id = payload.get("command_id") or correlation_id
        if not command_id:
            logger.warning(f"Received result without command_id or correlation_id: {payload}")
            return {"error": "Missing command_id", "status": "unknown"}

        raw_status = str(payload.get("status", "unknown")).lower()
        valid_states = [s.value for s in CommandState]
        status = raw_status if raw_status in valid_states else CommandState.UNKNOWN.value

        device_id = payload.get("device_id")
        action = payload.get("action")
        result = payload.get("result", {})
        error = payload.get("error")
        evidence = payload.get("evidence")

        # 1. Update SQLite command record
        self.storage.update_command_state(
            command_id=command_id,
            state=status,
            result=result,
            error=error
        )

        # 2. Update device_registry state when execution completes
        if status == CommandState.COMPLETED.value and device_id:
            power_state = result.get("power_state") or result.get("state")
            if power_state and action in ["set_power", "turn_on", "turn_off"]:
                device_registry.set_power_state(device_id, power_state)

        # 3. Generate speech outcome
        dev_info = device_registry.get_device(device_id) if device_id else None
        dev_name = dev_info.get("name") if dev_info else (device_id or "the device")
        speech_outcome = generate_speech_outcome(
            device_name=dev_name,
            action=action or "set_power",
            state=status,
            result=result,
            error=error
        )

        outcome = {
            "schema_version": "1.0",
            "command_id": command_id,
            "device_id": device_id,
            "device_name": dev_name,
            "action": action,
            "status": status,
            "result": result,
            "error": error,
            "evidence": evidence,
            "speech_outcome": speech_outcome
        }

        # 4. Notify async listeners
        command_tracker.notify_result(command_id, outcome)
        logger.info(f"Processed result for command {command_id}: status='{status}', outcome='{speech_outcome}'")
        return outcome

    async def start(self):
        """Start listening for RN Hub device execution results."""
        channel = await self.get_channel()
        if not channel or channel.is_closed:
            logger.info("CommandResultConsumer: No active broker channel available; running with in-process notifications.")
            return

        target_queue = settings.rabbitmq_result_queue or "results"
        target_exchange = settings.rabbitmq_result_exchange or settings.rabbitmq_command_exchange
        target_routing_key = settings.rabbitmq_result_routing_key or "results"

        queue = await channel.declare_queue(target_queue, durable=True)
        if target_exchange:
            exchange = await channel.declare_exchange(
                target_exchange,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            await queue.bind(exchange, routing_key=target_routing_key)

        async def _consume_loop():
            self.is_running = True
            logger.info(f"CommandResultConsumer listening on queue '{target_queue}'...")
            try:
                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            try:
                                payload = json.loads(message.body.decode("utf-8"))
                                self.process_result_payload(
                                    payload,
                                    correlation_id=message.correlation_id
                                )
                            except Exception as e:
                                logger.error(f"Error parsing incoming result message: {e}")
            except asyncio.CancelledError:
                pass
            finally:
                self.is_running = False

        self._consume_task = asyncio.create_task(_consume_loop())

    async def stop(self):
        """Stop listening for results."""
        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
        self.is_running = False


consumer = RabbitMQConsumer()
result_consumer = CommandResultConsumer()
