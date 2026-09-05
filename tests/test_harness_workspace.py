import pytest
import sys
from pathlib import Path

from test_harness.manager import test_harness_manager
from test_harness.workspace_orchestrator.jira_runner import jira_ticket_workspace_runner
from test_harness.workspace_orchestrator.tester import workspace_orchestrator_tester


def test_test_harness_manager_registration():
    """Verifies that the workspace orchestrator tester and jira runner are registered."""
    assert hasattr(test_harness_manager, "workspace_orchestrator_tester")
    assert hasattr(test_harness_manager, "jira_ticket_runner")
    assert test_harness_manager.workspace_orchestrator_tester.name == "workspace_orchestrator_tester"
    assert test_harness_manager.workspace_orchestrator_tester.status.value == "active"


def test_jira_ticket_workspace_runner_prompt_new():
    """Runs a test ticket with PROMPT_NEW mode on LOCAL_CONTAINER."""
    res = jira_ticket_workspace_runner.run_and_verify_ticket(
        ticket_key="HARNESS-101",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        cleanup_after=True,
        verbose=False
    )
    assert res["success"] is True
    assert res["ticket_key"] == "HARNESS-101"
    assert res["mode"] == "PROMPT_NEW"
    assert res["target_platform"] == "LOCAL_CONTAINER"
    assert res["verifications"]["directory_created"] is True
    assert res["verifications"]["git_branch_valid"] is True
    assert res["verifications"]["provider_rules_enforced"] is True
    assert res["verifications"]["staged_files_handled"] is True
    assert res["verifications"]["handoff_recorded"] is True
    assert res["verifications"]["jira_label_handled"] is True


def test_jira_ticket_workspace_runner_prompt_existing():
    """Runs a test ticket with PROMPT mode on GOOGLE_JULES."""
    res = jira_ticket_workspace_runner.run_and_verify_ticket(
        ticket_key="HARNESS-202",
        mode="PROMPT",
        target_platform="GOOGLE_JULES",
        cleanup_after=True,
        verbose=False
    )
    assert res["success"] is True
    assert res["ticket_key"] == "HARNESS-202"
    assert res["mode"] == "PROMPT"
    assert res["target_platform"] == "GOOGLE_JULES"
    assert res["branch_name"] == "jira-HARNESS-202-agent"
    assert res["verifications"]["git_branch_valid"] is True
    assert res["verifications"]["provider_rules_enforced"] is True


def test_jira_ticket_workspace_runner_codex():
    """Runs a test ticket with CODEX_CLOUD platform."""
    res = jira_ticket_workspace_runner.run_and_verify_ticket(
        ticket_key="HARNESS-303",
        mode="PROMPT_NEW",
        target_platform="CODEX_CLOUD",
        cleanup_after=True,
        verbose=False
    )
    assert res["success"] is True
    assert res["target_platform"] == "CODEX_CLOUD"
    assert res["verifications"]["provider_rules_enforced"] is True


def test_workspace_orchestrator_tester_matrix():
    """Verifies matrix testing across platforms in the test harness component."""
    summary = workspace_orchestrator_tester.test_all_platforms(verbose=False)
    assert summary["all_passed"] is True
    assert summary["total_tested"] == 6
    for r in summary["results"]:
        assert r["success"] is True
