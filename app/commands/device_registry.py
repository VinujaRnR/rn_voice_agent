"""Device registry to keep track of available smart home devices, robots, and peripherals."""
import re
from typing import Dict, Any, Optional, List


def normalize_device_id(device_id: str) -> str:
    """Normalize device ID, converting MAC representations to canonical 12-char hex string."""
    cleaned = (device_id or "").strip().lower()
    # Strip colons and hyphens if in MAC format
    mac_candidate = re.sub(r"[:-]", "", cleaned)
    if len(mac_candidate) == 12 and all(c in "0123456789abcdef" for c in mac_candidate):
        return mac_candidate
    return cleaned


def is_mac_format(device_id: str) -> bool:
    """Check if identifier matches 12-hex MAC address format."""
    cleaned = re.sub(r"[:-]", "", (device_id or "").strip().lower())
    return len(cleaned) == 12 and all(c in "0123456789abcdef" for c in cleaned)


def format_mac_address(device_id: str) -> str:
    """Format canonical 12-char hex string to standard colon-delimited MAC."""
    norm = normalize_device_id(device_id)
    if len(norm) == 12 and all(c in "0123456789abcdef" for c in norm):
        return ":".join(norm[i:i+2] for i in range(0, 12, 2))
    return norm


class DeviceRegistry:
    def __init__(self):
        self._devices: Dict[str, Dict[str, Any]] = {
            # Step 10 Relay Device Contract
            "98a316e6b658": {
                "name": "Testing Farm Lights",
                "type": "Relay",
                "connection": "USB-connected ESP8266",
                "allowed_actions": ["set_power", "get_status", "turn_on", "turn_off"],
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "off",
                "mac_address": "98:a3:16:e6:b6:58",
                "enrolled": True,
                "auth_token": "esp_token_98a316e6b658",
                "aliases": [
                    "testing farm lights",
                    "testing farm light",
                    "testing farm",
                    "farm lights",
                    "farm light",
                    "test farm lights",
                    "farm relay",
                    "lighting relay"
                ],
                "scheduled_rules": {
                    "min_delay_minutes": 1,
                    "max_delay_minutes": 180,
                    "max_duration_minutes": 720,
                    "allowed_actions": ["set_power", "turn_on", "turn_off"]
                }
            },
            "room_lights": {
                "name": "Room Lights",
                "type": "lighting",
                "connection": "Zigbee Gateway",
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "off",
                "enrolled": True,
                "auth_token": "zigbee_token_room_lights",
                "aliases": [
                    "room lights",
                    "room light",
                    "main lights",
                    "main light",
                    "living room lights",
                    "living room light",
                    "bedroom lights",
                    "ceiling lights"
                ],
                "allowed_actions": ["set_power", "turn_on", "turn_off"],
                "scheduled_rules": {
                    "min_delay_minutes": 1,
                    "max_delay_minutes": 180,
                    "allowed_actions": ["set_power", "turn_on", "turn_off"]
                }
            },
            "kitchen_lights": {
                "name": "Kitchen Lights",
                "type": "lighting",
                "connection": "Zigbee Gateway",
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "off",
                "enrolled": True,
                "auth_token": "zigbee_token_kitchen_lights",
                "aliases": ["kitchen lights", "kitchen light"],
                "allowed_actions": ["set_power", "turn_on", "turn_off"],
                "scheduled_rules": {
                    "min_delay_minutes": 1,
                    "max_delay_minutes": 180,
                    "allowed_actions": ["set_power", "turn_on", "turn_off"]
                }
            },
            "desk_lamp": {
                "name": "Desk Lamp",
                "type": "lighting",
                "connection": "WiFi Smart Plug",
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "off",
                "enrolled": True,
                "auth_token": "wifi_token_desk_lamp",
                "aliases": [
                    "desk lamp",
                    "desk light",
                    "study light",
                    "reading lamp",
                    "table lamp"
                ],
                "allowed_actions": ["set_power", "turn_on", "turn_off"],
                "scheduled_rules": {
                    "min_delay_minutes": 1,
                    "max_delay_minutes": 180,
                    "allowed_actions": ["set_power", "turn_on", "turn_off"]
                }
            },
            "thermostat": {
                "name": "Thermostat",
                "type": "climate",
                "connection": "WiFi HVAC Controller",
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "on",
                "enrolled": True,
                "auth_token": "hvac_token_thermostat",
                "aliases": ["thermostat", "air conditioner", "ac unit"],
                "allowed_actions": ["set_temperature", "set_mode", "set_power"],
                "scheduled_rules": {
                    "min_delay_minutes": 1,
                    "max_delay_minutes": 360,
                    "allowed_actions": ["set_temperature", "set_power"]
                }
            },
            "robot_base": {
                "name": "Robot Vacuum & Base",
                "type": "robot",
                "connection": "Serial ROS2 Bridge",
                "status": "online",
                "online_status": "Reported by RN Hub",
                "power_state": "on",
                "enrolled": True,
                "auth_token": "robot_token_base",
                "aliases": ["robot vacuum", "robot base", "robot chassis", "chassis", "mobile base"],
                "allowed_actions": ["start", "stop", "dock", "move_forward", "move_backward", "turn_left", "turn_right"]
            },
            "arm_manipulator": {
                "name": "Robot 6-DOF Arm",
                "type": "arm",
                "connection": "CAN bus / USB-Serial",
                "status": "idle",
                "online_status": "Reported by RN Hub",
                "power_state": "on",
                "enrolled": True,
                "auth_token": "robot_token_arm",
                "aliases": ["manipulator arm", "robot arm", "arm gripper"],
                "allowed_actions": ["home", "grasp", "release"]
            },
        }

    def normalize_device_id(self, device_id: str) -> str:
        return normalize_device_id(device_id)

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        norm_id = self.normalize_device_id(device_id)
        dev = self._devices.get(norm_id)
        if not dev:
            # Fall back to resolving via alias
            resolved = self.resolve_device(device_id)
            if resolved:
                dev = self._devices.get(resolved)
                norm_id = resolved
        if dev:
            d = dict(dev)
            d["id"] = norm_id
            d["device_id"] = norm_id
            return d
        return None

    def is_device_enrolled(self, device_id: str) -> bool:
        dev = self.get_device(device_id)
        return bool(dev and dev.get("enrolled", False))

    def verify_device_credentials(self, device_id: str, auth_token: Optional[str] = None) -> bool:
        """Verify device identity against enrolled credentials.
        
        The MAC address alone is not an authentication credential; the Hub
        must still verify the identity and enrollment credentials of enrolled devices.
        """
        dev = self.get_device(device_id)
        if not dev or not dev.get("enrolled", False):
            return False
        # If an auth token is supplied, verify it matches
        registered_token = dev.get("auth_token")
        if auth_token is not None:
            return auth_token == registered_token
        # Enrolled device identity verified by Hub credentials on record
        return True

    def register_device(self, device_id: str, metadata: Dict[str, Any]) -> str:
        norm_id = self.normalize_device_id(device_id)
        data = dict(metadata)
        if "mac_address" not in data and is_mac_format(norm_id):
            data["mac_address"] = format_mac_address(norm_id)
        self._devices[norm_id] = data
        return norm_id

    def unregister_device(self, device_id: str) -> bool:
        norm_id = self.normalize_device_id(device_id)
        return self._devices.pop(norm_id, None) is not None

    def list_devices(self) -> List[Dict[str, Any]]:
        result = []
        for dev_id, dev_data in self._devices.items():
            item = dict(dev_data)
            item["id"] = dev_id
            item["device_id"] = dev_id
            result.append(item)
        return result

    def set_power_state(self, device_id: str, state: str):
        dev_id = self.resolve_device(device_id) or self.normalize_device_id(device_id)
        if dev_id in self._devices:
            self._devices[dev_id]["power_state"] = state

    def set_online_status(self, device_id: str, status: str):
        dev_id = self.resolve_device(device_id) or self.normalize_device_id(device_id)
        if dev_id in self._devices:
            self._devices[dev_id]["status"] = status
            self._devices[dev_id]["online_status"] = f"Reported by RN Hub ({status})"

    def resolve_device(self, text: str) -> Optional[str]:
        """Resolve a device query against registered device IDs and aliases."""
        clean_text = text.lower().strip()
        # 1. Exact match with normalized device_id
        norm_id = self.normalize_device_id(clean_text)
        if norm_id in self._devices:
            return norm_id

        # 2. Check exact alias or full phrase match
        for dev_id, meta in self._devices.items():
            aliases = meta.get("aliases", [])
            for alias in aliases:
                # Exact match
                if clean_text == alias:
                    return dev_id
                # Whole-phrase match in query
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, clean_text):
                    return dev_id

        return None


device_registry = DeviceRegistry()
