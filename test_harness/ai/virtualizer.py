import re
import time
from typing import Dict, Any, List, Optional
from backend.harness.base import BaseCodingHarness, HarnessResult
from test_harness.base import BaseTestComponent, ComponentStatus

class AIServiceVirtualizer(BaseCodingHarness, BaseTestComponent):
    """
    AI Service Virtualizer: Simulates real-world AI agent/LLM behaviors,
    including network latency simulation, failure injection, semantic branching,
    clarification requests, and token tracking.
    """

    def __init__(self, name: str = "ai_virtualizer"):
        BaseTestComponent.__init__(self, name=name)
        self.latency_seconds: float = 0.0
        self.should_fail: bool = False
        self.failure_reason: str = "Simulated AI Service Error"
        self.total_tokens_consumed: int = 0
        self.execution_count: int = 0
        self.allowed_domains = ["github.com", "pypi.org", "gitlab.com"]
        self.status = ComponentStatus.ACTIVE

    def inject_latency(self, seconds: float):
        """Configure simulated AI response latency."""
        self.latency_seconds = max(0.0, seconds)

    def inject_failure(self, reason: str = "RateLimitError: simulated rate limit exceeded"):
        """Configure the virtualizer to simulate an AI provider error."""
        self.should_fail = True
        self.failure_reason = reason

    def clear_failure(self):
        """Clears any simulated failure mode."""
        self.should_fail = False

    def run_task(
        self,
        prompt: str,
        container_info: Dict[str, Any],
        project_config: Dict[str, Any],
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None
    ) -> HarnessResult:
        self.execution_count += 1

        # Simulate latency if configured
        if self.latency_seconds > 0:
            time.sleep(self.latency_seconds)

        # Estimate virtual token consumption (roughly 4 chars per token)
        prompt_tokens = len(prompt) // 4
        self.total_tokens_consumed += prompt_tokens

        # Simulated failure mode
        if self.should_fail:
            return HarnessResult(
                status="failed",
                summary_changes="",
                full_log=f"[AI Virtualizer: Error] {self.failure_reason}"
            )

        # 1. Virtualize Security Boundary: External Network Access
        urls = re.findall(r"https?://([a-zA-Z0-9.-]+)", prompt)
        for domain in urls:
            if domain not in self.allowed_domains:
                # Check if approval exists in chat_context
                is_approved = any(
                    "approved" in msg.get("content", "").lower() and domain in msg.get("content", "")
                    for msg in (chat_context or [])
                )
                if not is_approved:
                    return HarnessResult(
                        status="paused_waiting_input",
                        paused_reason="external_access_requested",
                        question_for_user=f"Virtual AI requires external network access to https://{domain}. Do you approve?",
                        requested_permission={"type": "network_access", "domain": domain},
                        full_log=f"[AI Virtualizer] Paused for domain approval: {domain}"
                    )

        # 2. Virtualize Clarification Questions
        if prompt.strip().endswith("?") and ("how" in prompt.lower() or "which" in prompt.lower()):
            return HarnessResult(
                status="paused_waiting_input",
                paused_reason="question",
                question_for_user=f"[Virtual AI Clarification] {prompt}",
                full_log="[AI Virtualizer] Paused requesting user clarification."
            )

        # 3. Virtualize Code Generation Completion
        completion_tokens = 150
        self.total_tokens_consumed += completion_tokens

        diff = f"""diff --git a/virtual_solution.py b/virtual_solution.py
new file mode 100644
--- /dev/null
+++ b/virtual_solution.py
@@ -0,0 +1,8 @@
+# Virtualized solution generated for: {project_config.get('key', 'APP')}
+def virtual_feature():
+    # Implemented based on prompt: {prompt[:40]}...
+"""
        summary = f"Implemented virtual solution for ticket in project {project_config.get('name', 'Default')}."
        if system_prompt_additions:
            summary += f" (Adhered to system prompt additions: {system_prompt_additions})"

        return HarnessResult(
            status="completed",
            summary_changes=summary,
            what_was_wrong="Virtual defect diagnosed.",
            what_was_done="Synthesized virtual code changes.",
            user_check_items=["Verify virtual code against acceptance criteria"],
            git_diff=diff,
            full_log=f"[AI Virtualizer] Completed virtual task. Tokens consumed: {self.total_tokens_consumed}"
        )

    def reset(self):
        self.latency_seconds = 0.0
        self.should_fail = False
        self.total_tokens_consumed = 0
        self.execution_count = 0
