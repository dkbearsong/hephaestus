import logging
from typing import Dict, Any, Optional, List, Literal
from pathlib import Path

from test_harness.base import BaseTestComponent, ComponentStatus
from test_harness.workspace_orchestrator.jira_runner import (
    JiraTicketWorkspaceRunner,
    jira_ticket_workspace_runner
)
from services.workspace_orchestrator import WorkspaceOrchestrator, workspace_orchestrator

logger = logging.getLogger("hephaestus.test_harness.workspace_orchestrator")


class WorkspaceOrchestratorTester(BaseTestComponent):
    """
    Test Harness component for validating the WorkspaceOrchestrator service,
    providing automated verification across all platforms (GOOGLE_JULES, CODEX_CLOUD,
    LOCAL_CONTAINER) and Jira test ticket execution.
    """

    def __init__(self, name: str = "workspace_orchestrator_tester"):
        super().__init__(name=name)
        self.orchestrator = workspace_orchestrator
        self.jira_runner = jira_ticket_workspace_runner
        self.status = ComponentStatus.ACTIVE

    def test_single_ticket(
        self,
        ticket_key: str = "PROJ-101",
        mode: Literal["PROMPT_NEW", "PROMPT"] = "PROMPT_NEW",
        target_platform: Literal["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"] = "LOCAL_CONTAINER",
        comment_text: Optional[str] = None,
        use_live_jira: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Runs a test Jira ticket and verifies the orchestrator behavior.
        """
        return self.jira_runner.run_and_verify_ticket(
            ticket_key=ticket_key,
            mode=mode,
            target_platform=target_platform,
            comment_text=comment_text,
            use_live_jira=use_live_jira,
            cleanup_after=True,
            verbose=verbose
        )

    def test_all_platforms(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Runs test tickets across all 3 platforms and both modes.
        """
        if verbose:
            print("\n" + "=" * 80)
            print("🚀 RUNNING WORKSPACE ORCHESTRATOR TEST SUITE ACROSS ALL PLATFORMS")
            print("=" * 80)

        test_matrix = [
            ("PROJ-NEW-JULES", "PROMPT_NEW", "GOOGLE_JULES"),
            ("PROJ-NEW-CODEX", "PROMPT_NEW", "CODEX_CLOUD"),
            ("PROJ-NEW-CONTAINER", "PROMPT_NEW", "LOCAL_CONTAINER"),
            ("PROJ-EXIST-JULES", "PROMPT", "GOOGLE_JULES"),
            ("PROJ-EXIST-CODEX", "PROMPT", "CODEX_CLOUD"),
            ("PROJ-EXIST-CONTAINER", "PROMPT", "LOCAL_CONTAINER"),
        ]

        results = []
        all_passed = True

        for ticket_key, mode, platform in test_matrix:
            try:
                res = self.jira_runner.run_and_verify_ticket(
                    ticket_key=ticket_key,
                    mode=mode,
                    target_platform=platform,
                    cleanup_after=True,
                    verbose=verbose
                )
                results.append(res)
                if not res.get("success"):
                    all_passed = False
            except Exception as e:
                all_passed = False
                logger.error(f"Failed test for {ticket_key}: {e}", exc_info=True)
                results.append({
                    "ticket_key": ticket_key,
                    "mode": mode,
                    "target_platform": platform,
                    "success": False,
                    "error": str(e)
                })

        if verbose:
            print("\n" + "=" * 80)
            print("📊 WORKSPACE ORCHESTRATOR MATRIX SUMMARY")
            print("=" * 80)
            print(f"{'TICKET KEY':<22} | {'MODE':<12} | {'PLATFORM':<18} | {'STATUS'}")
            print("-" * 80)
            for r in results:
                status_icon = "✅ PASSED" if r.get("success") else "❌ FAILED"
                print(f"{r['ticket_key']:<22} | {r['mode']:<12} | {r['target_platform']:<18} | {status_icon}")
            print("=" * 80)

        return {
            "all_passed": all_passed,
            "total_tested": len(results),
            "results": results
        }


workspace_orchestrator_tester = WorkspaceOrchestratorTester()
