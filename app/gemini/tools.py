"""Tool function definitions for Gemini 3.5 Flash-Lite function calling."""
from typing import List, Dict, Any

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_current_time",
        "description": "Get the current date and time for an IANA timezone or city name (e.g., 'Asia/Colombo', 'Tokyo', 'London').",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone or major city name, e.g. 'Asia/Colombo', 'Asia/Tokyo', 'Colombo', 'Tokyo'."
                }
            },
            "required": ["timezone"]
        }
    },
    {
        "name": "get_weather",
        "description": "Get real-time observed weather conditions, temperature, and short-term forecasts for a requested city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g., 'Colombo', 'Kandy', 'Tokyo'."
                },
                "forecast_days": {
                    "type": "integer",
                    "description": "Number of forecast days (1 to 5). Defaults to 1 for current weather."
                }
            },
            "required": ["city"]
        }
    },
    {
        "name": "search_web",
        "description": "Search the internet for latest news, websites, robotics research, current events, and changing facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query keywords or research topic."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_places",
        "description": "Find restaurants, cafés, shops, ratings, reviews, and locations around a city or area.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Type of cuisine, place category, or restaurant name (e.g., 'seafood', 'Italian', 'café')."
                },
                "location": {
                    "type": "string",
                    "description": "City or neighborhood name, e.g., 'Colombo', 'Colombo 03'."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_devices",
        "description": "Retrieve all registered and authorized IoT devices, lights, and robot actuators in the RN Hub network.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_device_status",
        "description": "Retrieve the actual live state (power, online status, parameters) of a specific device from RN Hub.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Hardware device ID or recognized name (e.g., '98a316e6b658', 'room_lights', 'farm_lights')."
                }
            },
            "required": ["device_id"]
        }
    },
    {
        "name": "control_device",
        "description": "Request an authorized device action (e.g. set power on/off, turn on lights) to be executed by RN Hub via RabbitMQ.",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Target device ID (e.g., '98a316e6b658', 'room_lights')."
                },
                "action": {
                    "type": "string",
                    "description": "Action name, e.g., 'set_power', 'turn_on', 'turn_off'."
                },
                "parameters": {
                    "type": "object",
                    "description": "Action parameters, e.g., {'state': 'on'}."
                }
            },
            "required": ["device_id", "action"]
        }
    },
    {
        "name": "schedule_device_action",
        "description": "Schedule a device action for a later time (e.g., 'turn them off after 20 minutes').",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Target device ID or name."
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform, e.g., 'turn_off', 'set_power'."
                },
                "delay_minutes": {
                    "type": "integer",
                    "description": "Delay in minutes before executing the action (e.g., 20)."
                },
                "parameters": {
                    "type": "object",
                    "description": "Optional parameters, e.g., {'state': 'off'}."
                }
            },
            "required": ["device_id", "action", "delay_minutes"]
        }
    },
    {
        "name": "set_reminder",
        "description": "Set a persistent scheduled reminder for the user when instructed to remind them about a task or event.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Clean reminder task description (e.g. 'take medicine', 'inspect the garden')."
                },
                "delay_minutes": {
                    "type": "number",
                    "description": "Delay in minutes until the reminder should trigger."
                },
                "delay_seconds": {
                    "type": "integer",
                    "description": "Optional delay in seconds until the reminder triggers."
                },
                "target_time": {
                    "type": "string",
                    "description": "Optional clock time (e.g. '4:30 PM', '16:00')."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "list_reminders",
        "description": "List all active, pending reminders currently scheduled for the user.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel or clear active scheduled reminders. If user says 'cancel reminder' or 'cancel reminders' without specifying which, set reminder_id='all'. If user specifies a task name (e.g. 'cancel oven reminder', 'cancel porridge reminder'), set reminder_id to that specific task keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "reminder_id": {
                    "type": "string",
                    "description": "Specific task keyword (e.g., 'oven', 'porridge', 'lights') or 'all' to cancel all active reminders."
                }
            }
        }
    },
    {
        "name": "search_past_conversations",
        "description": "Search user's previous conversations and references stored cryptographically hashed for future recall.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term, topic, or hash of previous conversation to recall."
                }
            },
            "required": ["query"]
        }
    }
]
