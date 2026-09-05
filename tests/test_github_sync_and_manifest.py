import json
import shutil
import tempfile
import pytest
from pathlib import Path

from services.models import (
    WorkspaceTriggerPayload,
    PrepSummary,
    HandoffState,
    HarnessManifest
)
from services.events import (
    event_bus,
    WORKSPACE_READY_FOR_AGENT,
    WORKSPACE_BLOCKED,
    GIT_LOG_STREAM
)
from services.github_service import GitHubService, GitHubAuthError
from services.scaffolding import GitRunner
from services.workspace_orchestrator import WorkspaceOrchestrator
from backend.jira_service.client import jira_service


@pytest.fixture
def temp_workspace():
    tmp = tempfile.mkdtemp(prefix="hephaestus_gh_test_")
    path = Path(tmp)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_staging(temp_workspace):
    stg = temp_workspace / "staging_task_abc"
    stg.mkdir(parents=True, exist_ok=True)
    (stg / "prompt.md").write_text("# Task Requirements\nImplement user auth.", encoding="utf-8")
    (stg / "preparations.md").write_text("Setup dependencies.", encoding="utf-8")
    (stg / "staged_files").mkdir(parents=True, exist_ok=True)
    (stg / "staged_files" / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
    return stg


def test_prep_blocked_halts_dispatch_and_emits_event(temp_workspace, sample_staging, monkeypatch):
    """
    If PrepSummary.status is BLOCKED:
    - Record failure (ready_for_execution=False)
    - Emit WORKSPACE_BLOCKED event
    - Post notification comment to Jira
    - Skip platform dispatch
    """
    emitted_events = []

    def on_blocked(data):
        emitted_events.append(data)

    event_bus.on(WORKSPACE_BLOCKED, on_blocked)

    jira_comments = []
    monkeypatch.setattr(jira_service, "add_comment", lambda key, comment: jira_comments.append((key, comment)))

    class BlockedAgent:
        def run(self, working_dir, branch_name, merged_instructions, prompt_md_path):
            return PrepSummary(
                status="BLOCKED",
                working_directory=str(working_dir),
                branch_name=branch_name,
                blocker_reason="Missing critical secret token in preparations"
            )

    orchestrator = WorkspaceOrchestrator(agent=BlockedAgent())

    payload = WorkspaceTriggerPayload(
        ticket_key="AUTH-BLOCKED-101",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        staging_dir=sample_staging,
        workspaces_root=temp_workspace / "workspaces"
    )

    handoff = orchestrator.orchestrate(payload)

    assert handoff.ready_for_execution is False
    assert handoff.prep_summary.status == "BLOCKED"

    # Verify event emitted
    assert len(emitted_events) == 1
    assert emitted_events[0]["ticket_key"] == "AUTH-BLOCKED-101"
    assert "Missing critical secret" in emitted_events[0]["reason"]

    # Verify Jira comment posted
    assert len(jira_comments) == 1
    assert jira_comments[0][0] == "AUTH-BLOCKED-101"
    assert "AI Preparation Blocked" in jira_comments[0][1]

    event_bus.off(WORKSPACE_BLOCKED, on_blocked)


def test_prep_ready_commits_and_creates_manifest(temp_workspace, sample_staging):
    """
    If PrepSummary.status is READY:
    - Commits staged modifications with chore(harness): initialize workspace for ${ticketKey}
    - Writes standardized harness_manifest.json with repo coordinates
    - Emits WORKSPACE_READY_FOR_AGENT carrying manifest path
    """
    ready_events = []

    def on_ready(data):
        ready_events.append(data)

    event_bus.on(WORKSPACE_READY_FOR_AGENT, on_ready)

    simulated_gh = GitHubService(token="mock_token_123", simulation_mode=True)
    orchestrator = WorkspaceOrchestrator(github=simulated_gh)

    payload = WorkspaceTriggerPayload(
        ticket_key="PROJ-READY-202",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        staging_dir=sample_staging,
        workspaces_root=temp_workspace / "workspaces"
    )

    handoff = orchestrator.orchestrate(payload)

    assert handoff.ready_for_execution is True
    working_dir = Path(handoff.working_directory)

    # 1. Verify commit in git log
    log_res = GitRunner.run_git(["log", "-n", "3", "--oneline"], cwd=working_dir)
    assert "chore(harness): initialize workspace for PROJ-READY-202" in log_res.stdout

    # 2. Verify harness_manifest.json
    manifest_file = working_dir / "harness_manifest.json"
    assert manifest_file.exists()

    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest = HarnessManifest(**manifest_data)
    assert manifest.ticket_key == "PROJ-READY-202"
    assert manifest.mode == "PROMPT_NEW"
    assert manifest.target_platform == "LOCAL_CONTAINER"
    assert manifest.repo_coordinates.branch == "main"
    assert manifest.repo_coordinates.commit_sha is not None
    assert len(manifest.repo_coordinates.commit_sha) == 40
    assert "prompt.md" in manifest.prompt_location.prompt_file

    # 3. Verify event emitted
    assert len(ready_events) == 1
    assert ready_events[0]["ticket_key"] == "PROJ-READY-202"
    assert ready_events[0]["manifest_path"] == str(manifest_file.resolve())

    event_bus.off(WORKSPACE_READY_FOR_AGENT, on_ready)


def test_prompt_existing_pushes_tracking_branch_when_remote_exists(temp_workspace, sample_staging):
    """
    In PROMPT mode, if an upstream remote exists, verifies pushing tracking branch
    to origin (e.g. jira-${ticketKey}-agent).
    """
    # 1. Create a bare upstream remote repo
    upstream_dir = temp_workspace / "upstream.git"
    upstream_dir.mkdir(parents=True, exist_ok=True)
    GitRunner.run_git(["init", "--bare", "-b", "main"], cwd=upstream_dir)

    # Seed upstream main
    seed_dir = temp_workspace / "seed_repo"
    seed_dir.mkdir(parents=True, exist_ok=True)
    GitRunner.run_git(["init", "-b", "main"], cwd=seed_dir)
    GitRunner.run_git(["config", "user.name", "Seeder"], cwd=seed_dir)
    GitRunner.run_git(["config", "user.email", "seed@org.internal"], cwd=seed_dir)
    (seed_dir / "README.md").write_text("# Upstream Repo\n", encoding="utf-8")
    GitRunner.run_git(["add", "."], cwd=seed_dir)
    GitRunner.run_git(["commit", "-m", "Initial upstream commit"], cwd=seed_dir)
    GitRunner.run_git(["remote", "add", "origin", str(upstream_dir.resolve())], cwd=seed_dir)
    GitRunner.run_git(["push", "-u", "origin", "main"], cwd=seed_dir)

    orchestrator = WorkspaceOrchestrator()

    payload = WorkspaceTriggerPayload(
        ticket_key="PROMPT-PUSH-303",
        mode="PROMPT",
        target_platform="LOCAL_CONTAINER",
        repo_url=str(upstream_dir.resolve()),
        staging_dir=sample_staging,
        workspaces_root=temp_workspace / "workspaces"
    )

    handoff = orchestrator.orchestrate(payload)
    assert handoff.ready_for_execution is True

    # Check that tracking branch exists on upstream
    branch_check = GitRunner.run_git(["branch", "-a"], cwd=upstream_dir)
    assert "jira-PROMPT-PUSH-303-agent" in branch_check.stdout


def test_git_log_streaming():
    """Verify that git commands stream stdout/stderr lines to the event bus."""
    streamed_lines = []

    def on_git_stream(data):
        streamed_lines.append(data["line"])

    event_bus.on(GIT_LOG_STREAM, on_git_stream)

    res = GitRunner.run_git(["version"], cwd=Path.cwd(), stream_logs=True)
    assert "git version" in res.stdout
    assert any("git version" in line for line in streamed_lines)

    event_bus.off(GIT_LOG_STREAM, on_git_stream)


def test_missing_github_token_fails_fast_when_not_simulated():
    """Verify GitHubService fails fast with GitHubAuthError if token is absent and not in simulation."""
    gh = GitHubService(token="", simulation_mode=False)
    assert gh.is_authenticated() is False
    with pytest.raises(GitHubAuthError) as exc_info:
        gh.create_remote_repository("test-repo-failure")
    assert "GITHUB_TOKEN" in str(exc_info.value)
