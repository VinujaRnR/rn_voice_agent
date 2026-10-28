"""RabbitMQ consumer for processing inbound robot events."""
import json
import aio_pika
from typing import Callable, Awaitable


class RabbitMQConsumer:
    def __init__(self, channel: aio_pika.abc.AbstractChannel):
        self.channel = channel

    async def consume(self, queue_name: str, callback: Callable[[dict], Awaitable[None]]):
        queue = await self.channel.declare_queue(queue_name, durable=True)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    payload = json.loads(message.body.decode())
                    await callback(payload)
