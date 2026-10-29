"""RN Hub Simulator and Result Publisher.

Simulates the RN Hub hardware controller side:
1. Consumes validated commands from RabbitMQ 'commands' queue.
2. Executes actions on enrolled IoT devices (e.g. ESP8266 lighting relay 98a316e6b658).
3. Produces concrete execution evidence.
4. Publishes execution results back to RabbitMQ 'results' queue.
"""
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import aio_pika
from app.config import settings
from app.rabbitmq.connection import rabbitmq_connection

logger = logging.getLogger(__name__)


class RNHubSimulator:
    """Simulates RN Hub command processing and result publishing."""

    def __init__(self, connection_manager=None):
        self.connection_manager = connection_manager or rabbitmq_connection
        self._consume_task: Optional[asyncio.Task] = None
        self.is_running = False

    def execute_device_action(self, command_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate hardware execution on enrolled IoT device and produce execution evidence."""
        command_id = command_payload.get("command_id", "unknown_cmd")
        device_id = command_payload.get("device_id", "")
        action = command_payload.get("action") or command_payload.get("actions", "")
        params = command_payload.get("parameters") if "parameters" in command_payload else command_payload.get("params", {})

        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 10 & 12 Hardware Target: Lighting Relay 98a316e6b658
        if device_id in ["98a316e6b658", "98:a3:16:e6:b6:58"]:
            if action in ["set_power", "turn_on", "turn_off"]:
                state = params.get("state")
                if action == "turn_on":
                    state = "on"
                elif action == "turn_off":
                    state = "off"

                if state in ["on", "off"]:
                    return {
                        "schema_version": "1.0",
                        "command_id": command_id,
                        "device_id": "98a316e6b658",
                        "device_name": "Testing Farm Lights",
                        "device_type": "Relay",
                        "connection": "USB-connected ESP8266",
                        "action": "set_power",
                        "status": "completed",
                        "result": {
                            "state": state,
                            "power_state": state,
                            "gpio_pin": 12,
                            "relay_contact": "closed" if state == "on" else "open",
                            "voltage_mv": 3300
                        },
                        "evidence": f"esp8266_relay_contact_{state}",
                        "error": None,
                        "timestamp": now_iso
                    }
                else:
                    return {
                        "schema_version": "1.0",
                        "command_id": command_id,
                        "device_id": "98a316e6b658",
                        "action": "set_power",
                        "status": "rejected",
                        "result": {},
                        "evidence": None,
                        "error": f"Invalid power state '{state}'. Expected 'on' or 'off'.",
                        "timestamp": now_iso
                    }

            elif action == "get_status":
                return {
                    "schema_version": "1.0",
                    "command_id": command_id,
                    "device_id": "98a316e6b658",
                    "action": "get_status",
                    "status": "completed",
                    "result": {
                        "status": "online",
                        "power_state": "off",
                        "uptime_seconds": 86400
                    },
                    "evidence": "esp8266_heartbeat_verified",
                    "error": None,
                    "timestamp": now_iso
                }
            else:
                return {
                    "schema_version": "1.0",
                    "command_id": command_id,
                    "device_id": "98a316e6b658",
                    "action": action,
                    "status": "rejected",
                    "result": {},
                    "error": f"Action '{action}' is not supported on lighting relay.",
                    "timestamp": now_iso
                }

        # Device not found
        return {
            "schema_version": "1.0",
            "command_id": command_id,
            "device_id": device_id,
            "action": action,
            "status": "rejected",
            "result": {},
            "error": f"Device '{device_id}' is not enrolled in RN Hub.",
            "timestamp": now_iso
        }

    async def publish_result(
        self,
        result_payload: Dict[str, Any],
        reply_to: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> bool:
        """Publish execution result to RabbitMQ results queue for the voice assistant."""
        channel = await self.connection_manager.get_channel()
        command_id = correlation_id or result_payload.get("command_id")

        if channel and not channel.is_closed:
            try:
                target_exchange = settings.rabbitmq_result_exchange or settings.rabbitmq_command_exchange
                target_key = reply_to or settings.rabbitmq_result_routing_key or "results"

                msg = aio_pika.Message(
                    body=json.dumps(result_payload).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    correlation_id=command_id
                )

                if target_exchange:
                    exchange = await channel.declare_exchange(
                        target_exchange,
                        aio_pika.ExchangeType.TOPIC,
                        durable=True
                    )
                    await exchange.publish(msg, routing_key=target_key)
                else:
                    await channel.default_exchange.publish(msg, routing_key=target_key)

                logger.info(f"[RN Hub Simulator] Published result for {command_id} to '{target_key}': status={result_payload.get('status')}")
                return True
            except Exception as e:
                logger.error(f"[RN Hub Simulator] Failed to publish result: {e}")
                return False
        else:
            # In offline mock mode: dispatch directly to in-process result consumer
            logger.info(f"[RN Hub Simulator Mock] Directly dispatching result for {command_id}: {result_payload.get('status')}")
            from app.rabbitmq.consumer import result_consumer
            result_consumer.process_result_payload(result_payload, correlation_id=command_id)
            return True

    async def process_and_reply(self, command_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute action on simulated hardware and publish device result back."""
        result = self.execute_device_action(command_payload)
        await self.publish_result(
            result,
            correlation_id=command_payload.get("command_id")
        )
        return result


hub_simulator = RNHubSimulator()
