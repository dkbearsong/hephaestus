import os
import shutil
import subprocess
import tempfile
import pytest
from pathlib import Path

from services.models import (
    WorkspaceTriggerPayload,
    PrepSummary,
    ProviderConfig,
    HandoffState
)
from services.scaffolding import ScaffoldingEngine, GitRunner
from services.provider_prep import ProviderPrepEngine
from services.prep_agent import PreparationAgent
from services.workspace_orchestrator import WorkspaceOrchestrator


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="hephaestus_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_staging(temp_dir):
    staging = temp_dir / "staging_task_123"
    staging.mkdir(parents=True)
    
    # prompt.md
    (staging / "prompt.md").write_text(
        "# Task\nImplement JWT authentication endpoint in auth.py\n",
        encoding="utf-8"
    )
    
    # preparations.md
    (staging / "preparations.md").write_text(
        "Move auth_helper.py to services/auth/\nInstall pyjwt\n",
        encoding="utf-8"
    )
    
    # staged_files/
    staged = staging / "staged_files"
    staged.mkdir()
    (staged / "auth_helper.py").write_text("# Auth helper code\n", encoding="utf-8")
    (staged / "run_tests.sh").write_text("#!/bin/bash\npytest\n", encoding="utf-8")
    (staged / ".env.staging").write_text("API_SECRET=supersecret123\n", encoding="utf-8")
    
    return staging


def test_models_validation(temp_dir):
    payload = WorkspaceTriggerPayload(
        ticket_key="PROJ-999",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        staging_dir=temp_dir / "staging",
        workspaces_root=temp_dir / "workspaces"
    )
    assert payload.ticket_key == "PROJ-999"
    assert payload.mode == "PROMPT_NEW"
    assert payload.target_platform == "LOCAL_CONTAINER"
    assert payload.repo_url is None

    summary = PrepSummary(
        status="READY",
        working_directory=str(temp_dir),
        branch_name="main",
        detected_commands={"build": None, "test": "pytest", "lint": None},
        files_modified=["services/auth/auth_helper.py"]
    )
    assert summary.status == "READY"
    assert summary.detected_commands["test"] == "pytest"


def test_scaffolding_prompt_new(temp_dir, sample_staging):
    engine = ScaffoldingEngine()
    workspaces_root = temp_dir / "workspaces"
    
    payload = WorkspaceTriggerPayload(
        ticket_key="PROJ-NEW",
        mode="PROMPT_NEW",
        target_platform="GOOGLE_JULES",
        staging_dir=sample_staging,
        workspaces_root=workspaces_root
    )
    
    res = engine.setup_workspace(payload)
    working_dir = res["working_directory"]
    
    assert working_dir.exists()
    assert (working_dir / ".git").exists()
    assert (working_dir / ".gitignore").exists()
    assert (working_dir / "README.md").exists()
    assert (working_dir / "LICENSE").exists()
    assert (working_dir / ".jules" / "config.yaml").exists()
    
    # Staged assets should be copied directly to workspace root in PROMPT_NEW
    assert (working_dir / "auth_helper.py").exists()
    assert (working_dir / "run_tests.sh").exists()
    assert res["branch_name"] == "main"
    assert res["inbox_directory"] is None


def test_scaffolding_prompt_existing_repo(temp_dir, sample_staging):
    # Setup a dummy upstream bare or local repo
    upstream_dir = temp_dir / "upstream_repo"
    upstream_dir.mkdir()
    GitRunner.run_git(["init", "-b", "main"], cwd=upstream_dir)
    GitRunner.run_git(["config", "user.name", "Tester"], cwd=upstream_dir)
    GitRunner.run_git(["config", "user.email", "tester@test.com"], cwd=upstream_dir)
    (upstream_dir / "app.py").write_text("print('hello')", encoding="utf-8")
    GitRunner.run_git(["add", "."], cwd=upstream_dir)
    GitRunner.run_git(["commit", "-m", "Initial upstream commit"], cwd=upstream_dir)
    
    engine = ScaffoldingEngine()
    workspaces_root = temp_dir / "workspaces"
    
    payload = WorkspaceTriggerPayload(
        ticket_key="PROJ-456",
        mode="PROMPT",
        target_platform="CODEX_CLOUD",
        repo_url=str(upstream_dir),
        staging_dir=sample_staging,
        workspaces_root=workspaces_root
    )
    
    res = engine.setup_workspace(payload)
    working_dir = res["working_directory"]
    
    assert working_dir.exists()
    assert (working_dir / "app.py").exists()
    assert res["branch_name"] == "jira-PROJ-456-agent"
    
    # Tracking branch should be active
    branch_res = GitRunner.run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=working_dir)
    assert branch_res.stdout.strip() == "jira-PROJ-456-agent"
    
    # In PROMPT mode, assets must go into .harness_inbox/
    assert (working_dir / ".harness_inbox" / "auth_helper.py").exists()
    assert not (working_dir / "auth_helper.py").exists()


def test_provider_prep_google_jules(temp_dir, sample_staging):
    prep_engine = ProviderPrepEngine()
    repo_dir = temp_dir / "jules_repo"
    repo_dir.mkdir()
    GitRunner.run_git(["init", "-b", "main"], cwd=repo_dir)
    GitRunner.run_git(["config", "user.name", "Tester"], cwd=repo_dir)
    GitRunner.run_git(["config", "user.email", "tester@test.com"], cwd=repo_dir)
    (repo_dir / "test_main.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    GitRunner.run_git(["add", "."], cwd=repo_dir)
    GitRunner.run_git(["commit", "-m", "init"], cwd=repo_dir)
    
    config = prep_engine.prepare(
        working_dir=repo_dir,
        target_platform="GOOGLE_JULES",
        staging_dir=sample_staging,
        ticket_key="JULES-101"
    )
    
    assert config.platform == "GOOGLE_JULES"
    assert (repo_dir / ".jules" / "config.yaml").exists()
    assert (repo_dir / "pytest.ini").exists()
    
    # Verify zero uncommitted files rule
    status_res = GitRunner.run_git(["status", "--porcelain"], cwd=repo_dir)
    assert status_res.stdout.strip() == ""


def test_provider_prep_codex_cloud(temp_dir, sample_staging):
    prep_engine = ProviderPrepEngine()
    repo_dir = temp_dir / "codex_repo"
    repo_dir.mkdir()
    
    config = prep_engine.prepare(
        working_dir=repo_dir,
        target_platform="CODEX_CLOUD",
        staging_dir=sample_staging,
        ticket_key="CODEX-202"
    )
    
    assert config.platform == "CODEX_CLOUD"
    assert (repo_dir / ".codex" / "task_metadata.json").exists()
    assert (repo_dir / "main.py").exists() # Verified entry point was created
    assert "main.py" in config.entry_points_verified


def test_provider_prep_local_container(temp_dir, sample_staging):
    prep_engine = ProviderPrepEngine()
    repo_dir = temp_dir / "container_repo"
    repo_dir.mkdir()
    
    # Create an execution script without +x
    script_path = repo_dir / "run.sh"
    script_path.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    os.chmod(script_path, 0o644)
    
    config = prep_engine.prepare(
        working_dir=repo_dir,
        target_platform="LOCAL_CONTAINER",
        staging_dir=sample_staging,
        ticket_key="CONTAINER-303"
    )
    
    assert config.platform == "LOCAL_CONTAINER"
    assert (repo_dir / ".docker" / "mounts.json").exists()
    assert (repo_dir / ".env").exists()
    
    # Verify .env export from staging
    env_content = (repo_dir / ".env").read_text(encoding="utf-8")
    assert "API_SECRET=supersecret123" in env_content
    
    # Verify chmod +x on execution scripts
    assert os.access(script_path, os.X_OK)


def test_prep_agent_file_relocation_and_dependencies(temp_dir):
    agent = PreparationAgent()
    working_dir = temp_dir / "prep_workspace"
    working_dir.mkdir()
    
    # Setup .harness_inbox
    inbox = working_dir / ".harness_inbox"
    inbox.mkdir()
    (inbox / "auth_helper.py").write_text("# auth code\n", encoding="utf-8")
    
    # Existing requirements.txt
    (working_dir / "requirements.txt").write_text("fastapi>=0.100\n", encoding="utf-8")
    (working_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    
    instructions = "Move auth_helper.py to services/auth/\nInstall pyjwt\n"
    
    summary = agent.run(
        working_dir=working_dir,
        branch_name="jira-AUTH-1-agent",
        merged_instructions=instructions
    )
    
    assert summary.status == "READY"
    assert (working_dir / "services" / "auth" / "auth_helper.py").exists()
    assert not inbox.exists()
    
    req_content = (working_dir / "requirements.txt").read_text(encoding="utf-8")
    assert "pyjwt" in req_content
    assert summary.detected_commands["test"] == "pytest"


def test_workspace_orchestrator_end_to_end(temp_dir, sample_staging):
    orchestrator = WorkspaceOrchestrator()
    workspaces_root = temp_dir / "workspaces"
    
    payload = WorkspaceTriggerPayload(
        ticket_key="PAY-777",
        mode="PROMPT_NEW",
        target_platform="LOCAL_CONTAINER",
        staging_dir=sample_staging,
        workspaces_root=workspaces_root
    )
    
    handoff = orchestrator.orchestrate(payload)
    
    assert isinstance(handoff, HandoffState)
    assert handoff.ticket_key == "PAY-777"
    assert handoff.ready_for_execution is True
    assert handoff.branch_name == "main"
    assert Path(handoff.working_directory).exists()
    assert (Path(handoff.working_directory) / ".hephaestus_handoff.json").exists()
    assert (Path(handoff.working_directory) / ".harness" / "merged_preparations.md").exists()
    assert handoff.prep_summary.status == "READY"
