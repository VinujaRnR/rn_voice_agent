"""RabbitMQ connection manager using aio-pika."""
import aio_pika
from typing import Optional


class RabbitMQConnection:
    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.amqp_url)
        self.channel = await self.connection.channel()

    async def close(self):
        if self.connection:
            await self.connection.close()
