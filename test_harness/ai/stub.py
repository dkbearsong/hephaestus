from typing import Dict, Any, List, Optional
from backend.harness.base import BaseCodingHarness, HarnessResult
from test_harness.base import BaseTestComponent, ComponentStatus

class AIStubHarness(BaseCodingHarness, BaseTestComponent):
    """
    AI Stub Harness: Provides canned, predetermined responses for the AI portion.
    Zero external network calls, zero non-determinism.
    """

    def __init__(
        self,
        name: str = "ai_stub",
        status: str = "completed",
        summary_changes: str = "[STUB] Automated test changes applied successfully.",
        git_diff: str = "diff --git a/stub.py b/stub.py\n+ # Stub modification",
        question_for_user: Optional[str] = None,
        requested_permission: Optional[Dict[str, Any]] = None
    ):
        BaseTestComponent.__init__(self, name=name)
        self.canned_status = status
        self.canned_summary_changes = summary_changes
        self.canned_git_diff = git_diff
        self.canned_question_for_user = question_for_user
        self.canned_requested_permission = requested_permission
        self.status = ComponentStatus.ACTIVE

    def configure_stub(
        self,
        status: str = "completed",
        summary_changes: Optional[str] = None,
        git_diff: Optional[str] = None,
        question_for_user: Optional[str] = None,
        requested_permission: Optional[Dict[str, Any]] = None
    ):
        """Reconfigures the canned stub response."""
        self.canned_status = status
        if summary_changes is not None:
            self.canned_summary_changes = summary_changes
        if git_diff is not None:
            self.canned_git_diff = git_diff
        self.canned_question_for_user = question_for_user
        self.canned_requested_permission = requested_permission

    def run_task(
        self,
        prompt: str,
        container_info: Dict[str, Any],
        project_config: Dict[str, Any],
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None
    ) -> HarnessResult:
        return HarnessResult(
            status=self.canned_status,
            summary_changes=self.canned_summary_changes,
            what_was_wrong="Identified by AI Stub.",
            what_was_done="Resolved by AI Stub.",
            user_check_items=["Verify stub behavior"],
            git_diff=self.canned_git_diff,
            full_log=f"[AI Stub] Executed task for {container_info.get('container_name')}",
            question_for_user=self.canned_question_for_user,
            requested_permission=self.canned_requested_permission
        )

    def reset(self):
        self.canned_status = "completed"
        self.canned_question_for_user = None
        self.canned_requested_permission = None
