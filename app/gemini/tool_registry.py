"""Tool registry registering tool definitions, schemas, and execution handlers."""
from dataclasses import dataclass
from typing import Dict, Any, Callable, Type, Optional, List
from pydantic import BaseModel

from app.gemini.tool_schemas import (
    GetCurrentTimeArgs,
    GetWeatherArgs,
    SearchWebArgs,
    SearchPlacesArgs,
    ListDevicesArgs,
    GetDeviceStatusArgs,
    ControlDeviceArgs,
    ScheduleDeviceActionArgs,
    SetReminderArgs,
    ListRemindersArgs,
    CancelReminderArgs,
    SearchPastConversationsArgs,
    FamilyContactArgs,
    MedicationScheduleArgs,
    SafetyCheckArgs,
    FindLocalProviderArgs,
    PlayMusicArgs
)


@dataclass
class ToolDefinition:
    name: str
    description: str
    schema_class: Type[BaseModel]
    handler: Callable
    is_sensitive: bool = False


class ToolRegistry:
    """Central registry of validated tools available to Sarah AI."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        schema_class: Type[BaseModel],
        handler: Callable,
        is_sensitive: bool = False
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            schema_class=schema_class,
            handler=handler,
            is_sensitive=is_sensitive
        )

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def has_tool(self, name: str) -> bool:
        return name in self._tools


tool_registry = ToolRegistry()
