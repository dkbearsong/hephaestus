"""
Event Bus & Lifecycle Emitter for Hephaestus Workspace Orchestration.
Supports typed event emissions (WORKSPACE_READY_FOR_AGENT, WORKSPACE_BLOCKED, GIT_LOG_STREAM)
and decoupling Web UI status loggers and notifications.
"""

import inspect
import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger("hephaestus.services.events")

# Standard event names
WORKSPACE_READY_FOR_AGENT = "WORKSPACE_READY_FOR_AGENT"
WORKSPACE_BLOCKED = "WORKSPACE_BLOCKED"
GIT_LOG_STREAM = "GIT_LOG_STREAM"


class EventEmitter:
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def on(self, event: str, listener: Callable) -> None:
        """Registers an event listener callback."""
        if event not in self._listeners:
            self._listeners[event] = []
        if listener not in self._listeners[event]:
            self._listeners[event].append(listener)

    def off(self, event: str, listener: Callable) -> None:
        """Unregisters an event listener callback."""
        if event in self._listeners and listener in self._listeners[event]:
            self._listeners[event].remove(listener)

    def emit(self, event: str, data: Any = None) -> None:
        """Dispatches event to all registered listeners."""
        listeners = self._listeners.get(event, [])
        for listener in list(listeners):
            try:
                res = listener(data)
                # If an async coroutine function was passed, we warn or handle safely
                if inspect.iscoroutine(res):
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as e:
                logger.error(f"[EventEmitter] Error in listener for '{event}': {e}", exc_info=True)

    def clear(self) -> None:
        """Clears all registered listeners."""
        self._listeners.clear()


# Global singleton event bus
event_bus = EventEmitter()
