"""
Comprehensive test suite for ExecutionProfileEngine, ContainerSetupService,
Platform-Specific Execution Profiles, and Modular MCP Optional Helpers.
"""

import os
import stat
import json
import subprocess
import pytest
from pathlib import Path

from profiles.base import (
    TargetPlatform,
    ContainerSpec,
    PlatformConfig,
    ExecutionProfile,
    ValidationResult,
    apply_baseline_environment
)
from profiles.registry import (
    get_execution_profile,
    inject_profile_configurations,
    validate_profile_environment,
    strip_json_comments,
    generate_repo_tree,
    PROFILES_REGISTRY
)
from profiles.engine import ExecutionProfileEngine, execution_profile_engine
from services.container_factory import (
    ContainerSetupService,
    container_setup_service,
    ContainerSetupResult
)
from mcp_tools.optional_helpers import (
    run_package_audit,
    detect_test_runner,
    scaffold_github_workflow,
    scaffold_devcontainer,
    generate_task_directive,
    verify_container_health
)


@pytest.fixture
def clean_workspace(tmp_path):
    """Provides an isolated Git workspace for testing."""
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(ws), capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.name", "Test Agent"], cwd=str(ws), capture_output=True, text=True, check=False)
    subprocess.run(["git", "config", "user.email", "agent@test.internal"], cwd=str(ws), capture_output=True, text=True, check=False)
    return ws


# ==============================================================================
# 1. BASELINE ENVIRONMENT TESTS
# ==============================================================================

def test_baseline_environment_setup(clean_workspace):
    """Verifies deterministic baseline configuration applied across containers."""
    res = apply_baseline_environment(
        working_dir=clean_workspace,
        prompt_content="Implement authentication refactor",
        task_context="Ticket PROJ-101 details"
    )
    assert res["success"] is True

    # 1. Base Utilities checked
    assert "git" in res["base_utilities"]
    assert "curl" in res["base_utilities"]
    assert "jq" in res["base_utilities"]

    # 2. .gitignore defaults
    gitignore = clean_workspace / ".gitignore"
    assert gitignore.exists()
    gitignore_text = gitignore.read_text(encoding="utf-8")
    assert "__pycache__/" in gitignore_text
    assert ".venv/" in gitignore_text
    assert ".env" in gitignore_text

    # 3. Populated .harness/ directory
    harness_dir = clean_workspace / ".harness"
    assert harness_dir.exists()
    prompt_file = harness_dir / "prompt.md"
    task_context_file = harness_dir / "task_context.md"
    assert prompt_file.exists()
    assert task_context_file.exists()
    assert "authentication refactor" in prompt_file.read_text(encoding="utf-8")
    assert "PROJ-101" in task_context_file.read_text(encoding="utf-8")

    # 4. Permission normalization
    test_sub = clean_workspace / "src"
    test_sub.mkdir()
    test_file = test_sub / "main.py"
    test_file.write_text("print('hello')")
    # Re-apply to verify normalization on new files
    res2 = apply_baseline_environment(clean_workspace)
    assert res2["normalized_count"] > 0


# ==============================================================================
# 2. PLATFORM-SPECIFIC EXECUTION PROFILES
# ==============================================================================

def test_platform_registry_lookup():
    """Verifies that all 6 target platforms are registered and support aliases."""
    for plat in TargetPlatform:
        prof = get_execution_profile(plat)
        assert prof is not None
        assert prof.platform == plat

    # Test alias and case insensitivity
    assert get_execution_profile("jules").platform == TargetPlatform.GOOGLE_JULES
    assert get_execution_profile("codex").platform == TargetPlatform.CODEX_CLOUD
    assert get_execution_profile("local_container").platform == TargetPlatform.LOCAL_CONTAINER
    assert get_execution_profile("grok").platform == TargetPlatform.GROK_BUILD
    assert get_execution_profile("devin").platform == TargetPlatform.DEVIN_AI
    assert get_execution_profile("cursor").platform == TargetPlatform.CURSOR_DEVCONTAINER


def test_google_jules_profile(clean_workspace):
    """
    Profile: GOOGLE_JULES
    Injections: .jules/config.yaml specifying instructions, branch, build/test commands.
    Validation: Remote tracking branch must be synchronized, zero uncommitted files.
    """
    context = {
        "ticket_key": "PROJ-JULES-101",
        "branch_name": "jira-PROJ-JULES-101-agent",
        "test_command": "pytest -v",
        "build_command": "pip install -e .",
        "instructions": "Add rate limiter middleware"
    }
    injected = inject_profile_configurations(TargetPlatform.GOOGLE_JULES, clean_workspace, context)
    assert ".jules/config.yaml" in injected

    cfg_file = clean_workspace / ".jules" / "config.yaml"
    assert cfg_file.exists()
    cfg_text = cfg_file.read_text(encoding="utf-8")
    assert "PROJ-JULES-101" in cfg_text
    assert "pytest -v" in cfg_text

    # Validation when clean
    subprocess.run(["git", "add", "."], cwd=str(clean_workspace), check=False)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(clean_workspace), check=False)
    val = validate_profile_environment(TargetPlatform.GOOGLE_JULES, clean_workspace, context)
    assert val.valid is True

    # Validation when dirty (zero uncommitted files rule violated)
    dirty_file = clean_workspace / "dirty.txt"
    dirty_file.write_text("uncommitted work")
    val_dirty = validate_profile_environment(TargetPlatform.GOOGLE_JULES, clean_workspace, context)
    assert val_dirty.valid is False
    assert any("uncommitted" in err.lower() for err in val_dirty.errors)


def test_codex_cloud_profile(clean_workspace):
    """
    Profile: CODEX_CLOUD
    Injections: .codex/task.json, .github/prompts/, PR template stub.
    Validation: Top-level project descriptors exist for remote runners.
    """
    context = {
        "ticket_key": "PROJ-CODEX-202",
        "test_command": "npm test",
        "instructions": "Refactor token parsing"
    }
    injected = inject_profile_configurations(TargetPlatform.CODEX_CLOUD, clean_workspace, context)
    assert ".codex/task.json" in injected
    assert ".github/prompts/task_directive.prompt.md" in injected
    assert ".github/pull_request_template.md" in injected

    # Validation fails without top-level descriptor
    val_missing = validate_profile_environment(TargetPlatform.CODEX_CLOUD, clean_workspace, context)
    assert val_missing.valid is False
    assert any("descriptor" in err.lower() for err in val_missing.errors)

    # Add top-level descriptor (e.g., pyproject.toml)
    (clean_workspace / "pyproject.toml").write_text('[project]\nname = "test-pkg"\nversion = "0.1.0"\n')
    val_ok = validate_profile_environment(TargetPlatform.CODEX_CLOUD, clean_workspace, context)
    assert val_ok.valid is True


def test_local_container_profile(clean_workspace):
    """
    Profile: LOCAL_CONTAINER
    Injections: non-root user setup (UID 1000), pre-warmed toolchains, agent CLI binary config,
    real-time output streaming hook, .docker/mounts.json, Dockerfile, docker-compose.yml.
    Validation: Workspace is writable, resource limits (--memory=4g --cpus=2) enforced.
    """
    context = {"ticket_key": "PROJ-LOCAL-303"}
    injected = inject_profile_configurations(TargetPlatform.LOCAL_CONTAINER, clean_workspace, context)
    assert ".docker/mounts.json" in injected
    assert ".docker/stream_logs.sh" in injected
    assert ".agent/config.json" in injected
    assert "Dockerfile" in injected
    assert "docker-compose.yml" in injected

    # Verify Dockerfile contains user developer (1000) and toolchains
    dockerfile_content = (clean_workspace / "Dockerfile").read_text(encoding="utf-8")
    assert "developer" in dockerfile_content
    assert "1000" in dockerfile_content
    assert "python3" in dockerfile_content
    assert "nodejs" in dockerfile_content
    assert "golang-go" in dockerfile_content
    assert "rust" in dockerfile_content.lower()

    # Verify mounts.json enforces resource limits
    mounts_data = json.loads((clean_workspace / ".docker" / "mounts.json").read_text(encoding="utf-8"))
    assert mounts_data["resource_limits"]["memory"] == "4g"
    assert mounts_data["resource_limits"]["cpus"] == 2.0
    assert mounts_data["user"] == "1000:1000"

    # Validation passes
    val = validate_profile_environment(TargetPlatform.LOCAL_CONTAINER, clean_workspace, context)
    assert val.valid is True


def test_grok_build_profile(clean_workspace):
    """
    Profile: GROK_BUILD
    Injections: .grok/build-config.json, repo_tree.txt.
    Validation: Target files declared in preparations.md are correctly mapped in build config.
    """
    # Create sample files
    (clean_workspace / "src").mkdir()
    (clean_workspace / "src" / "worker.py").write_text("# worker")
    (clean_workspace / "src" / "queue.py").write_text("# queue")

    context = {
        "ticket_key": "PROJ-GROK-404",
        "preparations": "Modify src/worker.py and add retry mechanism to src/queue.py",
        "test_command": "pytest"
    }
    injected = inject_profile_configurations(TargetPlatform.GROK_BUILD, clean_workspace, context)
    assert ".grok/build-config.json" in injected
    assert "repo_tree.txt" in injected

    # Verify structural map
    tree_text = (clean_workspace / "repo_tree.txt").read_text(encoding="utf-8")
    assert "worker.py" in tree_text
    assert "queue.py" in tree_text

    # Write preparations.md so validation can inspect declared files
    (clean_workspace / "preparations.md").write_text(context["preparations"])
    val = validate_profile_environment(TargetPlatform.GROK_BUILD, clean_workspace, context)
    assert val.valid is True

    # Verify validation fails if build-config is missing declared files
    cfg_file = clean_workspace / ".grok" / "build-config.json"
    bad_cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    bad_cfg["task_spec"]["target_files"] = ["unrelated.py"]
    cfg_file.write_text(json.dumps(bad_cfg))

    val_bad = validate_profile_environment(TargetPlatform.GROK_BUILD, clean_workspace, context)
    assert val_bad.valid is False
    assert any("not mapped" in err.lower() for err in val_bad.errors)


def test_devin_ai_profile(clean_workspace):
    """
    Profile: DEVIN_AI
    Injections: devin_instructions.md, reproducible scripts/devin_setup.sh, scripts/devin_test.sh.
    Validation: Injected scripts exist and have executable permissions (chmod +x).
    """
    context = {
        "ticket_key": "PROJ-DEVIN-505",
        "instructions": "Implement webhook retry logic",
        "test_command": "pytest tests/test_retry.py"
    }
    injected = inject_profile_configurations(TargetPlatform.DEVIN_AI, clean_workspace, context)
    assert "devin_instructions.md" in injected
    assert "scripts/devin_setup.sh" in injected
    assert "scripts/devin_test.sh" in injected

    # Verify executable permissions
    setup_sh = clean_workspace / "scripts" / "devin_setup.sh"
    test_sh = clean_workspace / "scripts" / "devin_test.sh"
    assert os.access(str(setup_sh), os.X_OK)
    assert os.access(str(test_sh), os.X_OK)

    val = validate_profile_environment(TargetPlatform.DEVIN_AI, clean_workspace, context)
    assert val.valid is True

    # Strip executable bit and verify validation catches it
    setup_sh.chmod(0o644)
    val_no_exec = validate_profile_environment(TargetPlatform.DEVIN_AI, clean_workspace, context)
    assert val_no_exec.valid is False
    assert any("executable" in err.lower() for err in val_no_exec.errors)


def test_cursor_devcontainer_profile(clean_workspace):
    """
    Profile: CURSOR_DEVCONTAINER
    Injections: .devcontainer/devcontainer.json (with customizations.cursor block, postCreateCommand),
    .devcontainer/Dockerfile.
    Validation: Parse devcontainer.json with comments stripped confirming valid JSON.
    """
    context = {
        "ticket_key": "PROJ-CURSOR-606",
        "base_image": "mcr.microsoft.com/devcontainers/python:3.12"
    }
    injected = inject_profile_configurations(TargetPlatform.CURSOR_DEVCONTAINER, clean_workspace, context)
    assert ".devcontainer/devcontainer.json" in injected
    assert ".devcontainer/Dockerfile" in injected

    dc_file = clean_workspace / ".devcontainer" / "devcontainer.json"
    raw_content = dc_file.read_text(encoding="utf-8")
    assert "//" in raw_content  # Contains JSONC comments

    # Parsing raw content with standard json.loads would fail if comments aren't stripped
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw_content)

    # Parsing with strip_json_comments succeeds
    clean_json = strip_json_comments(raw_content)
    parsed = json.loads(clean_json)
    assert "customizations" in parsed
    assert "cursor" in parsed["customizations"]
    assert "editorRules" in parsed["customizations"]["cursor"]

    # Validation check succeeds
    val = validate_profile_environment(TargetPlatform.CURSOR_DEVCONTAINER, clean_workspace, context)
    assert val.valid is True


# ==============================================================================
# 3. MODULAR MCP OPTIONAL HELPERS TESTS
# ==============================================================================

def test_run_package_audit(clean_workspace):
    """Tests run_package_audit on Python project."""
    (clean_workspace / "requirements.txt").write_text("pytest>=8.0.0\n")
    audit = run_package_audit(clean_workspace)
    assert "audits_performed" in audit
    assert len(audit["audits_performed"]) > 0
    assert audit["audits_performed"][0]["package_manager"] == "pip"


def test_detect_test_runner(clean_workspace):
    """Tests test runner detection for Pytest, Jest, Vitest, and Go."""
    # Pytest detection
    (clean_workspace / "pytest.ini").write_text("[pytest]\n")
    runner = detect_test_runner(clean_workspace)
    assert runner["primary_runner"] == "pytest"
    assert runner["test_command"] == "pytest"

    # Node detection
    (clean_workspace / "package.json").write_text('{\n  "scripts": {"test": "npm test"},\n  "devDependencies": {"vitest": "^1.0.0"}\n}\n')
    node_runner = detect_test_runner(clean_workspace)
    assert any(r["runner"] == "vitest" for r in node_runner["available_runners"])


def test_scaffold_github_workflow(clean_workspace):
    """Tests scaffolding GitHub Actions workflow YAML."""
    for wf_type in ["ci", "lint", "test"]:
        res = scaffold_github_workflow(workflow_type=wf_type, workspace_dir=clean_workspace)
        assert res["success"] is True
        wf_path = clean_workspace / ".github" / "workflows" / f"{wf_type}.yml"
        assert wf_path.exists()
        assert wf_type.upper() in wf_path.read_text(encoding="utf-8")


def test_scaffold_devcontainer(clean_workspace):
    """Tests scaffolding devcontainer files."""
    res = scaffold_devcontainer(
        base_image="python:3.12-slim",
        extensions=["ms-python.python"],
        post_create_cmd="pip install -r requirements.txt",
        workspace_dir=clean_workspace
    )
    assert res["success"] is True
    assert (clean_workspace / ".devcontainer" / "devcontainer.json").exists()
    assert (clean_workspace / ".devcontainer" / "Dockerfile").exists()


def test_generate_task_directive(clean_workspace):
    """Tests generating task directives for all 5 targets: devin, grok, cursor, jules, codex."""
    targets = ["devin", "grok", "cursor", "jules", "codex"]
    for t in targets:
        res = generate_task_directive(
            target=t,
            prompt_content="Fix database connection pool timeout",
            workspace_dir=clean_workspace,
            task_context={"ticket_key": f"TASK-{t.upper()}"}
        )
        assert res["success"] is True
        out_file = clean_workspace / res["target_file"]
        assert out_file.exists()
        assert "timeout" in out_file.read_text(encoding="utf-8").lower()


def test_verify_container_health(clean_workspace):
    """Tests container diagnostic health verification utility."""
    report = verify_container_health(clean_workspace)
    assert "status" in report
    assert report["status"] in ("HEALTHY", "DEGRADED", "UNHEALTHY")
    assert "disk_space" in report
    assert "memory" in report
    assert "network_egress" in report
    assert "binaries" in report
    assert "git" in report["binaries"]


# ==============================================================================
# 4. CONTAINER DISPATCHER & EXECUTION PROFILE ENGINE TESTS
# ==============================================================================

def test_execution_profile_engine_prepare_workspace(clean_workspace):
    """Tests end-to-end workspace preparation via ExecutionProfileEngine."""
    (clean_workspace / "pyproject.toml").write_text('[project]\nname="test"\n')
    report = execution_profile_engine.prepare_workspace(
        platform=TargetPlatform.CODEX_CLOUD,
        working_dir=clean_workspace,
        ticket_key="PROJ-PREP-707",
        prompt_content="Update pyproject dependencies",
        preparations_content="Ensure poetry/flit compatibility"
    )
    assert report["platform"] == "CODEX_CLOUD"
    assert report["valid"] is True
    assert len(report["injected_files"]) > 0
    assert (clean_workspace / ".harness" / "prompt.md").exists()


def test_container_setup_service_dispatch(clean_workspace):
    """Tests ContainerSetupService for both local sandbox and cloud targets."""
    # 1. Local container dispatch
    local_res = container_setup_service.setup_container_environment(
        platform=TargetPlatform.LOCAL_CONTAINER,
        workspace_dir=clean_workspace,
        ticket_key="PROJ-DISPATCH-LOCAL",
        prompt_content="Run local test suite"
    )
    assert local_res.success is True
    assert local_res.platform == "LOCAL_CONTAINER"
    assert local_res.resource_limits["memory"] == "4g"
    assert local_res.resource_limits["cpus"] == 2.0
    assert local_res.stream_log_path is not None

    # 2. Cloud target dispatch (Devin AI)
    devin_res = container_setup_service.setup_container_environment(
        platform=TargetPlatform.DEVIN_AI,
        workspace_dir=clean_workspace,
        ticket_key="PROJ-DISPATCH-DEVIN",
        prompt_content="Run Devin autonomous engineering session"
    )
    assert devin_res.success is True
    assert devin_res.platform == "DEVIN_AI"
    assert (clean_workspace / "devin_instructions.md").exists()
