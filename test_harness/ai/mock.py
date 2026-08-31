from typing import Dict, Any, List, Optional
from backend.harness.base import BaseCodingHarness, HarnessResult
from test_harness.base import BaseTestComponent, ComponentStatus

class AIMockHarness(BaseCodingHarness, BaseTestComponent):
    """
    AI Mock Harness: Records all interactions, parameters, and prompts
    passed to the AI coding harness, allowing assertions on behavior.
    """

    def __init__(self, name: str = "ai_mock"):
        BaseTestComponent.__init__(self, name=name)
        self.call_history: List[Dict[str, Any]] = []
        self.default_result = HarnessResult(
            status="completed",
            summary_changes="[MOCK] Recorded and executed prompt successfully.",
            what_was_wrong="Mock detected issue.",
            what_was_done="Mock verified implementation.",
            user_check_items=["Mock check 1"],
            git_diff="diff --git a/mock.py b/mock.py\n+ # Mock change",
            full_log="[AI Mock] Successfully recorded task execution."
        )
        self.result_queue: List[HarnessResult] = []
        self.status = ComponentStatus.ACTIVE

    def enqueue_result(self, result: HarnessResult):
        """Enqueues a specific HarnessResult to return on the next call."""
        self.result_queue.append(result)

    def set_default_result(self, result: HarnessResult):
        """Sets the fallback HarnessResult when queue is empty."""
        self.default_result = result

    def run_task(
        self,
        prompt: str,
        container_info: Dict[str, Any],
        project_config: Dict[str, Any],
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None
    ) -> HarnessResult:
        interaction = {
            "prompt": prompt,
            "container_info": container_info,
            "project_config": project_config,
            "system_prompt_additions": system_prompt_additions,
            "chat_context": chat_context or []
        }
        self.call_history.append(interaction)

        if self.result_queue:
            return self.result_queue.pop(0)
        return self.default_result

    @property
    def call_count(self) -> int:
        return len(self.call_history)

    def last_call(self) -> Optional[Dict[str, Any]]:
        return self.call_history[-1] if self.call_history else None

    def assert_called(self, times: Optional[int] = None):
        """Asserts that the mock was invoked."""
        if times is not None:
            assert len(self.call_history) == times, f"Expected {times} calls, got {len(self.call_history)}"
        else:
            assert len(self.call_history) > 0, "Expected mock to have been called at least once"

    def assert_prompt_contains(self, substring: str):
        """Asserts that the last recorded prompt contains the specified substring."""
        assert self.call_history, "No calls recorded on AI mock"
        last_prompt = self.call_history[-1]["prompt"]
        assert substring in last_prompt, f"Expected substring '{substring}' in prompt, got '{last_prompt}'"

    def assert_not_called(self):
        """Asserts that the mock was never called."""
        assert len(self.call_history) == 0, f"Expected 0 calls, got {len(self.call_history)}"

    def reset(self):
        self.call_history.clear()
        self.result_queue.clear()
