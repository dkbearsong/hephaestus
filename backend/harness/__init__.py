from backend.harness.base import BaseCodingHarness, HarnessResult
from backend.harness.antigravity_harness import AntigravityHeadlessHarness
from backend.harness.langgraph_harness import LangGraphHarness
from backend.harness.registry import HarnessRegistry, harness_registry

def get_active_harness() -> BaseCodingHarness:
    """Returns the currently active coding harness via the registry."""
    return harness_registry.get_active_harness()

def set_active_harness(harness):
    """Sets the active coding harness instance or registered name."""
    harness_registry.set_active_harness(harness)

def reset_active_harness():
    """Resets the active harness to default."""
    harness_registry.reset_active_harness()

__all__ = [
    "BaseCodingHarness",
    "HarnessResult",
    "AntigravityHeadlessHarness",
    "LangGraphHarness",
    "HarnessRegistry",
    "harness_registry",
    "get_active_harness",
    "set_active_harness",
    "reset_active_harness",
]
