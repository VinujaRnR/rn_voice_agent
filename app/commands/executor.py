"""Command executor for dispatching actions to robots/devices."""
from typing import Dict, Any


class CommandExecutor:
    def __init__(self, publisher=None):
        self.publisher = publisher

    async def execute(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if self.publisher:
            await self.publisher.publish("robot_commands", command)
        return {"status": "dispatched", "command": command}
