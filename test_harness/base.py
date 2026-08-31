from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

class ComponentStatus(str, Enum):
    IDLE = "idle"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    STOPPED = "stopped"
    ERROR = "error"

class BaseTestComponent(ABC):
    """
    Abstract base class for all pluggable test harness components.
    Provides lifecycle management, status reporting, and state reset hooks.
    """

    def __init__(self, name: str):
        self.name = name
        self.status = ComponentStatus.IDLE
        self.config: Dict[str, Any] = {}

    def initialize(self, config: Optional[Dict[str, Any]] = None):
        """Initializes the component with optional configuration."""
        self.config = config or {}
        self.status = ComponentStatus.INITIALIZED

    def reset(self):
        """Resets component in-memory state between tests."""
        pass

    def teardown(self):
        """Releases resources and stops the component."""
        self.status = ComponentStatus.STOPPED

    def get_status(self) -> Dict[str, Any]:
        """Returns component diagnostics and current lifecycle status."""
        return {
            "name": self.name,
            "status": self.status.value,
            "config": self.config
        }
