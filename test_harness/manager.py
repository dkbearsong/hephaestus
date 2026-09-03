import logging
from typing import Dict, Any, Optional
from backend.harness import set_active_harness, reset_active_harness
from test_harness.base import BaseTestComponent, ComponentStatus
from test_harness.ai.stub import AIStubHarness
from test_harness.ai.mock import AIMockHarness
from test_harness.ai.virtualizer import AIServiceVirtualizer
from test_harness.preparations.tester import PreparationsTester
from test_harness.coding_agents.tester import CodingAgentsTester
from test_harness.webhook.watcher_client import WebhookWatcherClient
from test_harness.webhook.live_template import LiveWebhookTemplate
from test_harness.webhook.validator import WebhookPayloadValidator
from test_harness.data.loader import TestDataLoader
from test_harness.reporters.file_logger import TestExecutionLogger

logger = logging.getLogger("hephaestus.test_harness")

class TestHarness(BaseTestComponent):
    """
    Central Test Harness Manager orchestrating component-based testing
    for Hephaestus, providing stubs, mocks, and service virtualizations for AI,
    preparations testing, coding agent testing (Google Jules, Grok Build, OpenAI Codex,
    Docker Sandbox, Devin, OpenHands), webhook testing clients, validators, and execution reporters.
    """
    __test__ = False

    def __init__(self, name: str = "hephaestus_test_harness"):
        super().__init__(name=name)
        # Component Registry
        self.ai_stub = AIStubHarness()
        self.ai_mock = AIMockHarness()
        self.ai_virtualizer = AIServiceVirtualizer()
        self.preparations_tester = PreparationsTester()
        self.coding_agents_tester = CodingAgentsTester()
        self.webhook_client = WebhookWatcherClient()
        self.live_template = LiveWebhookTemplate()
        self.payload_validator = WebhookPayloadValidator()
        self.data_loader = TestDataLoader()
        self.logger = TestExecutionLogger()

        self._active_ai_component: Optional[BaseTestComponent] = None
        self.status = ComponentStatus.ACTIVE

    def plug_in_ai_stub(
        self,
        status: str = "completed",
        summary: str = "[STUB] Changes applied.",
        git_diff: str = "diff --git a/stub.py b/stub.py",
        question: Optional[str] = None,
        permission: Optional[Dict[str, Any]] = None
    ) -> AIStubHarness:
        """Plugs AIStubHarness into the base code workflow engine."""
        self.ai_stub.configure_stub(
            status=status,
            summary_changes=summary,
            git_diff=git_diff,
            question_for_user=question,
            requested_permission=permission
        )
        set_active_harness(self.ai_stub)
        self._active_ai_component = self.ai_stub
        logger.info("[TestHarness] Plugged in AI Stub Harness")
        return self.ai_stub

    def plug_in_ai_mock(self) -> AIMockHarness:
        """Plugs AIMockHarness into the base code workflow engine."""
        self.ai_mock.reset()
        set_active_harness(self.ai_mock)
        self._active_ai_component = self.ai_mock
        logger.info("[TestHarness] Plugged in AI Mock Harness")
        return self.ai_mock

    def plug_in_ai_virtualizer(
        self,
        latency_seconds: float = 0.0,
        should_fail: bool = False,
        failure_reason: str = "Simulated Virtual AI Error"
    ) -> AIServiceVirtualizer:
        """Plugs AIServiceVirtualizer into the base code workflow engine."""
        self.ai_virtualizer.reset()
        self.ai_virtualizer.inject_latency(latency_seconds)
        if should_fail:
            self.ai_virtualizer.inject_failure(failure_reason)
        set_active_harness(self.ai_virtualizer)
        self._active_ai_component = self.ai_virtualizer
        logger.info("[TestHarness] Plugged in AI Service Virtualizer")
        return self.ai_virtualizer

    def unplug_ai(self):
        """Unplugs any active test AI harness, restoring production default."""
        reset_active_harness()
        self._active_ai_component = None
        logger.info("[TestHarness] Unplugged test AI harness, restored base code default")

    def reset_all(self):
        """Resets state across all registered test components."""
        self.ai_stub.reset()
        self.ai_mock.reset()
        self.ai_virtualizer.reset()
        self.preparations_tester.reset()
        self.webhook_client.reset()
        self.data_loader.reset()
        self.logger.reset()
        self.unplug_ai()

    def teardown(self):
        self.reset_all()
        self.live_template.teardown()
        super().teardown()

    def get_harness_status(self) -> Dict[str, Any]:
        """Returns comprehensive status of all subcomponents."""
        return {
            "harness": self.get_status(),
            "active_ai_component": self._active_ai_component.name if self._active_ai_component else "none",
            "components": {
                "ai_stub": self.ai_stub.get_status(),
                "ai_mock": self.ai_mock.get_status(),
                "ai_virtualizer": self.ai_virtualizer.get_status(),
                "preparations_tester": self.preparations_tester.get_status(),
                "coding_agents_tester": "ready",
                "webhook_client": self.webhook_client.get_status(),
                "live_template": self.live_template.get_status(),
                "payload_validator": self.payload_validator.get_status(),
                "data_loader": self.data_loader.get_status(),
                "logger": self.logger.get_status(),
            }
        }

# Default singleton instance
test_harness_manager = TestHarness()
