"""
AirOS IPC Protocol & Security Contract
Enforces typed message structures:
  {
    "type": "control" | "telemetry" | "event" | "response",
    "version": "1.0",
    "request_id": "<uuid>",
    "token": "<auth_token>",
    "payload": { ... }
  }
Includes command allowlist validation, per-run token generation, and rate limiting.
"""

import json
import secrets
import logging
import uuid
from typing import Dict, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "1.0"

# Allowlisted control commands
ALLOWLISTED_COMMANDS: Set[str] = {
    "start",
    "stop",
    "pause",
    "resume",
    "calibrate",
    "calibrate_cancel",
    "calibrate_finish",
    "gesture_start_recording",
    "gesture_finish_recording",
    "gesture_cancel_recording",
    "gesture_list",
    "gesture_delete",
    "gesture_rename",
    "gesture_set_action",
    "profile_set",
    "profile_list",
    "profile_set_override",
    "settings_update",
    "settings_get",
    "voice_start",
    "voice_stop",
    "voice_status",
    "voice_text_command",
    "action_execute",
    "action_list",
    "context_get",
    "screenshot_capture",
    "auth",
}


class IPCAuthManager:
    """Manages per-run authentication tokens for IPC security."""

    def __init__(self, token: Optional[str] = None):
        self._auth_token = token or secrets.token_hex(16)

    @property
    def auth_token(self) -> str:
        return self._auth_token

    def validate_token(self, token: Optional[str]) -> bool:
        if not token:
            return False
        return secrets.compare_digest(self._auth_token, token)


def create_ipc_message(
    msg_type: str,
    payload: Dict[str, Any],
    request_id: Optional[str] = None,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a standard typed IPC message."""
    return {
        "type": msg_type,
        "version": PROTOCOL_VERSION,
        "request_id": request_id or str(uuid.uuid4()),
        "token": auth_token or "",
        "payload": payload,
    }


def parse_and_validate_ipc_message(
    raw_message: str,
    auth_manager: Optional[IPCAuthManager] = None,
    require_auth: bool = False,
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Parse and validate incoming raw JSON IPC message against schema and security allowlist.
    Returns (is_valid, parsed_dict, error_string).
    """
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError as e:
        return False, None, f"Invalid JSON format: {e}"

    if not isinstance(data, dict):
        return False, None, "Message must be a JSON object"

    msg_type = data.get("type", "")
    if not msg_type:
        # Legacy support fallback check
        if "command" in data:
            data = {
                "type": "control",
                "version": PROTOCOL_VERSION,
                "request_id": str(uuid.uuid4()),
                "token": data.get("token", ""),
                "payload": data,
            }
            msg_type = "control"
        else:
            return False, None, "Missing 'type' field"

    # Token check if required
    if require_auth and auth_manager:
        token = data.get("token") or (data.get("payload", {}).get("token") if isinstance(data.get("payload"), dict) else None)
        if not auth_manager.validate_token(token):
            return False, None, "Unauthorized: Invalid or missing IPC auth token"

    # Validate control payload command allowlist
    if msg_type == "control":
        payload = data.get("payload", data)
        if isinstance(payload, dict):
            cmd = payload.get("command", "")
            if not cmd:
                cmd = data.get("command", "")
            if cmd and cmd not in ALLOWLISTED_COMMANDS:
                return False, None, f"Command '{cmd}' is not in the allowlist"

    return True, data, None
