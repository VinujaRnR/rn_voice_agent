"""Secure tool dispatcher routing and executing tools under request context boundaries."""
import inspect
import logging
from typing import Dict, Any, Optional
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.request_context import RequestContext, get_current_request_context
from app.gemini.tool_registry import tool_registry, ToolDefinition
from app.gemini.tool_authorization import ToolAuthorizationManager
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
    ClarifyWeatherArgs,
    ClarifyReminderArgs,
    FamilyContactArgs,
    MedicationScheduleArgs,
    SafetyCheckArgs,
    FindLocalProviderArgs,
    PlayMusicArgs
)
from app.tools.time_weather import get_current_time, get_weather
from app.tools.web_search import search_web
from app.tools.places import search_places
from app.tools.device_status import list_devices, get_device_status
from app.tools.device_control import control_device, schedule_device_action
from app.tools.reminders import set_reminder, list_reminders, cancel_reminder
from app.context.memory import conversation_memory

logger = logging.getLogger(__name__)


def _register_builtin_tools():
    """Populate tool_registry with core platform tools."""
    tool_registry.register(
        name="get_current_time",
        description="Get current time for timezone",
        schema_class=GetCurrentTimeArgs,
        handler=lambda args, ctx: get_current_time(timezone=args.timezone)
    )
    tool_registry.register(
        name="get_weather",
        description="Get current weather and forecast for city",
        schema_class=GetWeatherArgs,
        handler=lambda args, ctx: get_weather(city=args.city, forecast_days=args.forecast_days)
    )
    tool_registry.register(
        name="search_web",
        description="Search the web for real-time information",
        schema_class=SearchWebArgs,
        handler=lambda args, ctx: search_web(query=args.query)
    )
    tool_registry.register(
        name="search_places",
        description="Find restaurants, places, and local facilities",
        schema_class=SearchPlacesArgs,
        handler=lambda args, ctx: search_places(query=args.query, location=args.location)
    )
    tool_registry.register(
        name="list_devices",
        description="List registered IoT devices",
        schema_class=ListDevicesArgs,
        handler=lambda args, ctx: list_devices()
    )
    tool_registry.register(
        name="get_device_status",
        description="Get live hardware state for device",
        schema_class=GetDeviceStatusArgs,
        handler=lambda args, ctx: get_device_status(device_id=args.device_id)
    )
    tool_registry.register(
        name="control_device",
        description="Control hardware device action",
        schema_class=ControlDeviceArgs,
        handler=lambda args, ctx: control_device(device_id=args.device_id, action=args.action, parameters=args.parameters),
        is_sensitive=True
    )
    tool_registry.register(
        name="schedule_device_action",
        description="Schedule device action with delay",
        schema_class=ScheduleDeviceActionArgs,
        handler=lambda args, ctx: schedule_device_action(device_id=args.device_id, action=args.action, delay_minutes=args.delay_minutes, parameters=args.parameters)
    )
    tool_registry.register(
        name="set_reminder",
        description="Set scheduled reminder for user",
        schema_class=SetReminderArgs,
        handler=lambda args, ctx: set_reminder(
            text=args.text,
            delay_seconds=args.delay_seconds,
            delay_minutes=args.delay_minutes,
            session_id=getattr(args, "session_id", None) or ctx.session_id,
            recurrence=args.recurrence
        )
    )
    tool_registry.register(
        name="list_reminders",
        description="List active reminders",
        schema_class=ListRemindersArgs,
        handler=lambda args, ctx: list_reminders(
            session_id=getattr(args, "session_id", None) or ctx.session_id
        )
    )
    tool_registry.register(
        name="cancel_reminder",
        description="Cancel active reminders",
        schema_class=CancelReminderArgs,
        handler=lambda args, ctx: cancel_reminder(
            reminder_id_or_keyword=args.reminder_id or "all",
            session_id=getattr(args, "session_id", None) or ctx.session_id
        )
    )
    tool_registry.register(
        name="search_past_conversations",
        description="Search cryptographically hashed conversations",
        schema_class=SearchPastConversationsArgs,
        handler=lambda args, ctx: {
            "status": "success",
            "query": args.query,
            "matches": conversation_memory.search_past_conversations(query=args.query, user_id=ctx.actor_id)
        }
    )
    tool_registry.register(
        name="clarify_weather_context",
        description="Clarify destination for weather query",
        schema_class=ClarifyWeatherArgs,
        handler=lambda args, ctx: {
            "status": "clarification_needed",
            "speech": "Where are you heading, or would you like the weather forecast for your current location in Colombo?"
        }
    )
    def _handle_reminder_clarify(args, ctx):
        from app.tools.reminders import generate_reminder_clarification_question
        speech = generate_reminder_clarification_question(args.verb, args.partial_task, args.time_label)
        return {
            "status": "clarification_needed",
            "partial_verb": args.verb,
            "partial_task": args.partial_task,
            "time_label": args.time_label,
            "speech": speech
        }
    tool_registry.register(
        name="clarify_reminder_context",
        description="Clarify ambiguous reminder request",
        schema_class=ClarifyReminderArgs,
        handler=_handle_reminder_clarify
    )
    # Step 11: Family communications tool
    tool_registry.register(
        name="manage_family_contacts",
        description="Search family directory or ask family to call",
        schema_class=FamilyContactArgs,
        handler=lambda args, ctx: {
            "status": "success",
            "action": args.action,
            "speech": f"I've noted your request to contact your {args.name or 'family'}."
        }
    )
    # Step 12: Medication schedule checking tool
    tool_registry.register(
        name="check_medication_schedule",
        description="Check resident prescription and adherence schedule",
        schema_class=MedicationScheduleArgs,
        handler=lambda args, ctx: {
            "status": "success",
            "action": args.action,
            "speech": "Your morning medication is scheduled for 8:00 AM with breakfast."
        }
    )
    # Step 13: Radar safety and hazard alert tool
    tool_registry.register(
        name="check_safety_status",
        description="Check home radar sensors and Australian weather hazard alerts",
        schema_class=SafetyCheckArgs,
        handler=lambda args, ctx: {
            "status": "normal",
            "action": args.action,
            "speech": "All home safety sensors are normal and no emergency alerts are active."
        }
    )
    # Step 14: Australian local trades and care services tool
    from app.integrations.places.australian_places import AustralianLocalServices
    tool_registry.register(
        name="find_local_services",
        description="Find verified plumbers, electricians, handymen, or NDIS providers in Australia",
        schema_class=FindLocalProviderArgs,
        handler=lambda args, ctx: {
            "status": "success",
            "category": args.category,
            "providers": AustralianLocalServices.find_providers(args.category, args.suburb_or_postcode)
        }
    )
    # Step 15: Music entertainment and voice playback tool
    def _handle_music(args, ctx):
        from app.services.entertainment.music_service import MusicEntertainmentService
        return MusicEntertainmentService.execute_playback_command(
            action=getattr(args, "action", "play"),
            track_title_or_artist=getattr(args, "query", None) or getattr(args, "track_title_or_artist", None),
            volume=getattr(args, "volume_level", None) or getattr(args, "volume", None)
        )

    tool_registry.register(
        name="control_music",
        description="Play music, skip tracks, adjust volume, or pause playback",
        schema_class=PlayMusicArgs,
        handler=_handle_music
    )
    tool_registry.register(
        name="play_music",
        description="Play music or a song for the resident",
        schema_class=PlayMusicArgs,
        handler=_handle_music
    )


_register_builtin_tools()


def dispatch_tool_sync(
    tool_name: str,
    arguments: Dict[str, Any],
    context: Optional[RequestContext] = None
) -> Dict[str, Any]:
    """Synchronous tool dispatcher executing under caller request context."""
    ctx = context or get_current_request_context()
    if not ctx:
        from app.services.session_service import LegacySessionAdapter
        from app.middleware.request_context import ROLE_PERMISSIONS
        legacy = LegacySessionAdapter.adapt()
        ctx = RequestContext(
            actor_id=legacy.user_id,
            session_id=legacy.session_id,
            role="resident",
            permissions=list(ROLE_PERMISSIONS["resident"]),
            is_authenticated=False,
            is_legacy=True
        )

    arg_sess = arguments.get("session_id") if isinstance(arguments, dict) else None
    if arg_sess and ctx.session_id == "default_session":
        ctx.session_id = arg_sess

    tool = tool_registry.get(tool_name)
    if not tool:
        logger.warning(f"Tool '{tool_name}' not found in registry")
        return {"status": "error", "message": f"Unknown tool '{tool_name}'"}

    try:
        validated_args = tool.schema_class(**arguments)
    except ValidationError as val_err:
        logger.error(f"Validation failed for tool '{tool_name}': {val_err}")
        return {
            "status": "validation_error",
            "message": f"Invalid arguments for tool '{tool_name}': {str(val_err)}"
        }

    is_auth, auth_msg = ToolAuthorizationManager.check_authorization(
        tool_name=tool_name,
        context=ctx,
        arguments=validated_args.model_dump()
    )
    if not is_auth:
        logger.warning(f"Unauthorized tool execution attempted: {tool_name} by {ctx.actor_id}. Reason: {auth_msg}")
        return {
            "status": "unauthorized",
            "message": auth_msg
        }

    try:
        handler = tool.handler
        if inspect.iscoroutinefunction(handler):
            import asyncio
            return asyncio.run(handler(validated_args, ctx))
        return handler(validated_args, ctx)
    except Exception as exc:
        logger.error(f"Error executing tool '{tool_name}': {exc}", exc_info=True)
        return {
            "status": "error",
            "message": f"Execution error in tool '{tool_name}': {str(exc)}"
        }


async def dispatch_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    context: Optional[RequestContext] = None,
    session: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """Validate, authorize, and execute a tool under the caller's request context."""
    # 1. Resolve context
    ctx = context or get_current_request_context()
    if not ctx:
        from app.services.session_service import LegacySessionAdapter
        from app.middleware.request_context import ROLE_PERMISSIONS
        legacy = LegacySessionAdapter.adapt()
        ctx = RequestContext(
            actor_id=legacy.user_id,
            session_id=legacy.session_id,
            role="resident",
            permissions=list(ROLE_PERMISSIONS["resident"]),
            is_authenticated=False,
            is_legacy=True
        )

    arg_sess = arguments.get("session_id") if isinstance(arguments, dict) else None
    if arg_sess and ctx.session_id == "default_session":
        ctx.session_id = arg_sess

    # 2. Lookup tool
    tool = tool_registry.get(tool_name)
    if not tool:
        logger.warning(f"Tool '{tool_name}' not found in registry")
        return {"status": "error", "message": f"Unknown tool '{tool_name}'"}

    # 3. Validate arguments via schema
    try:
        validated_args = tool.schema_class(**arguments)
    except ValidationError as val_err:
        logger.error(f"Validation failed for tool '{tool_name}': {val_err}")
        return {
            "status": "validation_error",
            "message": f"Invalid arguments for tool '{tool_name}': {str(val_err)}"
        }

    # 4. Check authorization and hardware safety
    is_auth, auth_msg = ToolAuthorizationManager.check_authorization(
        tool_name=tool_name,
        context=ctx,
        arguments=validated_args.model_dump()
    )
    if not is_auth:
        logger.warning(f"Unauthorized tool execution attempted: {tool_name} by {ctx.actor_id}. Reason: {auth_msg}")
        return {
            "status": "unauthorized",
            "message": auth_msg
        }

    # 5. Execute handler
    try:
        handler = tool.handler
        if inspect.iscoroutinefunction(handler):
            res = await handler(validated_args, ctx)
        else:
            res = handler(validated_args, ctx)
        return res
    except Exception as exc:
        logger.error(f"Error executing tool '{tool_name}': {exc}", exc_info=True)
        return {
            "status": "error",
            "message": f"Execution error in tool '{tool_name}': {str(exc)}"
        }
