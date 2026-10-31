"""
plugins/smart_vision.py — Smart Vision Core plugin for ULTRON.

Provides on-demand screen and region capture with multimodal AI visual analysis,
two-stage human authorization (capture consent and transmission consent),
anti-forgery permission tokens, and strict protection against visual prompt injections.
"""
from __future__ import annotations

from typing import Any, Optional

from core.plugin_runtime import HostContext, PluginRuntime
from plugins._smart_vision_controller import SmartVisionController

PLUGIN = {
    "name": "smart_vision",
    "description": (
        "Captures and visually analyzes the computer screen or a specific region on demand to answer questions. "
        "Call when the user asks what is visible on the screen, to read text on screen, examine an image, "
        "inspect an application window, or look at a monitor. "
        "Does NOT take desktop actions, click, or execute code. "
        "Operates with explicit user consent."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {
                "type": "STRING",
                "description": "The specific question or instruction about what to analyze on the screen.",
            },
            "target": {
                "type": "STRING",
                "description": "Optional capture target: 'screen' (default primary), 'monitor_1', 'monitor_2', 'all', or 'region'.",
            },
            "region": {
                "type": "STRING",
                "description": "Optional bounding box 'x,y,w,h' when target is 'region'.",
            },
            "destination": {
                "type": "STRING",
                "description": "Optional multimodal model destination to query (default: gemini-2.5-flash).",
            },
        },
        "required": ["question"],
    },
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "core",
    "brief": "Analyze what is on screen on demand with explicit consent",
    "default_enabled": False,
    "icon": "eye",
    "category": "VISION",
    "tags": ["SENSITIVE"],
    "version": "v1.0",
}

PLUGIN_SETTINGS = {
    "namespace": "smart_vision",
    "title": "Smart Vision",
    "fields": [
        {
            "name": "default_destination",
            "label": "Default Analysis Model",
            "type": "STRING",
            "default": "gemini-2.5-flash",
        },
        {
            "name": "retention_ttl_s",
            "label": "Capture Memory Retention (seconds)",
            "type": "INT",
            "default": 60,
        },
    ],
}

_DEFAULT_CONTROLLER: Optional[SmartVisionController] = None


def create_runtime(context: Optional[HostContext] = None) -> PluginRuntime:
    """Factory called by the plugin loader to instantiate the plugin's stateful runtime."""
    global _DEFAULT_CONTROLLER
    controller = SmartVisionController(context=context)
    _DEFAULT_CONTROLLER = controller
    return controller


def get_runtime() -> Optional[SmartVisionController]:
    return _DEFAULT_CONTROLLER


def run(parameters: dict, player=None, session_memory=None, runtime: Optional[SmartVisionController] = None) -> str:
    """Execute on-demand vision analysis with two-stage consent.

    parameters: dict containing 'question', and optional 'target', 'region', 'destination'.
    player: JarvisUI instance (optional).
    session_memory: optional session memory.
    runtime: SmartVisionController instance (optional).
    """
    controller = runtime or _DEFAULT_CONTROLLER
    if controller is None:
        controller = create_runtime()

    question = str(parameters.get("question", "")).strip()
    if not question:
        return "Please specify what you would like me to look at on your screen."

    target = str(parameters.get("target", "screen")).strip().lower() or "screen"
    region = parameters.get("region")
    destination = parameters.get("destination")

    if player and hasattr(player, "write_log"):
        try:
            player.write_log(f"VISION: Analyzing screen for '{question[:40]}...'")
        except Exception:
            pass

    return controller.execute_vision_request(
        question=question,
        target=target,
        region=region,
        destination=destination,
        deadline_s=30.0,
    )
