import pytest
from backend.coding_agents.orchestrator import coding_agent_orchestrator
from test_harness.coding_agents.tester import coding_agents_tester, ALL_CODING_AGENTS

@pytest.mark.parametrize("agent_id", ALL_CODING_AGENTS)
def test_coding_agent_mock_execution(agent_id):
    """
    Verifies that each of the coding agent orchestrators:
      1. Correctly handles prompt passed in from Jira comments.
      2. Initiates its specialized containerized environment.
      3. Produces a unified git diff and review results.
      4. Cleans up its container resources.
    """
    res = coding_agents_tester.test_single_agent(agent_id, verbose=False)
    assert res["success"] is True
    assert res["step_results"]["prompt_validation"]["valid"] is True
    assert res["step_results"]["container_initiation"]["container_id"] is not None
    assert res["step_results"]["task_execution"]["has_diff"] is True
    assert res["step_results"]["container_cleanup"]["success"] is True

def test_cursor_dev_container_mode():
    """Verifies Cursor running in Dev Container mode (.devcontainer/devcontainer.json)."""
    agent = coding_agent_orchestrator.get_agent("cursor_dev_container")
    res = agent.run_task(prompt="<|prompt|> Optimize query performance inside dev container.")
    assert res.status == "completed"
    assert "dev container" in res.summary_changes.lower()
    assert res.git_diff != ""

def test_all_coding_agents_summary():
    """Verifies test_all_agents batch runner."""
    summary = coding_agents_tester.test_all_agents(verbose=False)
    assert summary["all_passed"] is True
    assert summary["total_tested"] == len(ALL_CODING_AGENTS)

def test_orchestrator_list_supported_agents():
    """Verifies listing of supported agents from the orchestrator."""
    agents = coding_agent_orchestrator.list_supported_agents()
    assert len(agents) == len(ALL_CODING_AGENTS)
    agent_ids = {a["agent_id"] for a in agents}
    assert agent_ids == set(ALL_CODING_AGENTS)

def test_manual_jira_webhook_test_execution():
    """Verifies that manual_jira_webhook_test executes through the workflow pipeline."""
    res = coding_agents_tester.run_manual_jira_webhook_test(
        jira_issue_key="PYTEST-101",
        comment_text="<|prompt|> Add pytest test coverage for rate limiter.\n<|preparations|> Check date/time.",
        target_agent="google_jules"
    )
    assert res["success"] is True
    assert res["pipeline_result"]["status"] == "review_ready"
    assert "google_jules" in res["pipeline_result"]["summary_changes"].lower() or "jules" in res["pipeline_result"]["summary_changes"].lower()
