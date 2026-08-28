from backend.config import preferences
from backend.harness.base import BaseCodingHarness
from backend.harness.antigravity_harness import AntigravityHeadlessHarness
from backend.harness.langgraph_harness import LangGraphHarness

def get_active_harness() -> BaseCodingHarness:
    active = preferences.harness.active.lower()
    if active == "langgraph_agent":
        return LangGraphHarness()
    # Default is Antigravity Headless Daemon + Remote Control Harness
    return AntigravityHeadlessHarness()
