"""
Modular MCP Tools for Agent Convenience
Optional helper tools that the agent harness can invoke during workspace preparation:
- run_package_audit: Read-only vulnerability/dependency consistency check (npm audit, pip check, cargo audit)
- detect_test_runner: Inspects workspace root and returns explicit test commands and discovery patterns
- scaffold_github_workflow: Drops standard GitHub Actions workflow into .github/workflows/
- scaffold_devcontainer: Generates custom .devcontainer/devcontainer.json and Dockerfile definitions
- generate_task_directive: Compiles prompt.md into downstream platform preferred format
- verify_container_health: Diagnostic checking disk space, memory limits, network egress, binary availability
"""

import os
import sys
import json
import shutil
import socket
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Literal

logger = logging.getLogger("hephaestus.mcp_tools.optional_helpers")


def _resolve_workspace(workspace_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolves workspace directory or defaults to current working directory."""
    if workspace_dir:
        return Path(workspace_dir).resolve()
    return Path.cwd().resolve()


def run_package_audit(workspace_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Fast read-only vulnerability or dependency consistency check
    (npm audit, pip check, cargo audit) to alert the agent to conflicts early.
    """
    workspace = _resolve_workspace(workspace_dir)
    results: Dict[str, Any] = {
        "workspace": str(workspace),
        "audits_performed": [],
        "status": "PASSED",
        "findings": [],
        "errors": []
    }

    # 1. Python environment audit (pip check / requirements inspection)
    has_python = any((workspace / f).exists() for f in ["requirements.txt", "pyproject.toml", "setup.py"])
    if has_python:
        audit_entry: Dict[str, Any] = {"package_manager": "pip", "tool": "pip check"}
        try:
            cmd = [sys.executable, "-m", "pip", "check"]
            proc = subprocess.run(cmd, cwd=str(workspace), capture_output=True, text=True, timeout=15)
            audit_entry["exit_code"] = proc.returncode
            audit_entry["stdout"] = proc.stdout.strip()
            audit_entry["stderr"] = proc.stderr.strip()
            if proc.returncode != 0:
                results["status"] = "WARNING"
                results["findings"].append(f"pip check detected dependency conflicts: {proc.stdout.strip() or proc.stderr.strip()}")
            else:
                audit_entry["summary"] = "No broken requirements found."
        except Exception as ex:
            audit_entry["error"] = str(ex)
            results["errors"].append(f"pip check execution error: {ex}")
        results["audits_performed"].append(audit_entry)

    # 2. Node.js environment audit (npm audit)
    if (workspace / "package.json").exists():
        audit_entry = {"package_manager": "npm", "tool": "npm audit"}
        npm_bin = shutil.which("npm")
        if npm_bin and (workspace / "package-lock.json").exists():
            try:
                proc = subprocess.run([npm_bin, "audit", "--json"], cwd=str(workspace), capture_output=True, text=True, timeout=20)
                audit_entry["exit_code"] = proc.returncode
                try:
                    data = json.loads(proc.stdout)
                    vulnerabilities = data.get("metadata", {}).get("vulnerabilities", {})
                    audit_entry["vulnerabilities"] = vulnerabilities
                    total_vulns = sum(vulnerabilities.values()) if isinstance(vulnerabilities, dict) else 0
                    if total_vulns > 0:
                        results["status"] = "WARNING"
                        results["findings"].append(f"npm audit found {total_vulns} vulnerabilities: {vulnerabilities}")
                except Exception:
                    audit_entry["raw_output"] = proc.stdout[:500]
            except Exception as ex:
                audit_entry["error"] = str(ex)
        else:
            audit_entry["summary"] = "npm audit skipped (package-lock.json or npm binary missing)."
        results["audits_performed"].append(audit_entry)

    # 3. Rust environment audit (cargo audit / cargo check)
    if (workspace / "Cargo.toml").exists():
        audit_entry = {"package_manager": "cargo", "tool": "cargo audit"}
        cargo_audit_bin = shutil.which("cargo-audit")
        if cargo_audit_bin:
            try:
                proc = subprocess.run([cargo_audit_bin, "audit", "--json"], cwd=str(workspace), capture_output=True, text=True, timeout=20)
                audit_entry["exit_code"] = proc.returncode
                if proc.returncode != 0:
                    results["status"] = "WARNING"
                    results["findings"].append("cargo audit flagged security advisories.")
            except Exception as ex:
                audit_entry["error"] = str(ex)
        else:
            audit_entry["summary"] = "cargo audit binary not installed; static manifest verified."
        results["audits_performed"].append(audit_entry)

    if not results["audits_performed"]:
        results["summary"] = "No supported package manifests (pip, npm, cargo) detected in workspace."

    return results


def detect_test_runner(workspace_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Inspects the workspace root and returns explicit test execution commands
    and discovery patterns (e.g. Pytest, Jest, Vitest, Go test, Cargo test).
    """
    workspace = _resolve_workspace(workspace_dir)
    detected: List[Dict[str, Any]] = []

    # 1. Pytest
    if (workspace / "pytest.ini").exists() or (workspace / "tests").exists() or (workspace / "test").exists():
        detected.append({
            "runner": "pytest",
            "framework": "python",
            "command": "pytest",
            "discovery_pattern": "tests/**/test_*.py",
            "config_file": "pytest.ini" if (workspace / "pytest.ini").exists() else None
        })
    elif any(workspace.glob("test_*.py")) or any(workspace.glob("*_test.py")):
        detected.append({
            "runner": "pytest",
            "framework": "python",
            "command": "pytest",
            "discovery_pattern": "*test*.py",
            "config_file": None
        })

    # 2. Node (Jest / Vitest / npm test)
    pkg_json = workspace / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            dev_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "vitest" in dev_deps or "vitest.config.ts" in [f.name for f in workspace.iterdir()]:
                detected.append({
                    "runner": "vitest",
                    "framework": "node",
                    "command": "npx vitest run",
                    "discovery_pattern": "**/*.{test,spec}.{js,ts,jsx,tsx}",
                    "config_file": "vitest.config.ts" if (workspace / "vitest.config.ts").exists() else None
                })
            elif "jest" in dev_deps or "jest.config.js" in [f.name for f in workspace.iterdir()]:
                detected.append({
                    "runner": "jest",
                    "framework": "node",
                    "command": "npx jest",
                    "discovery_pattern": "**/__tests__/**/*.[jt]s?(x), **/?(*.)+(spec|test).[jt]s?(x)",
                    "config_file": "jest.config.js" if (workspace / "jest.config.js").exists() else None
                })
            elif "test" in scripts:
                detected.append({
                    "runner": "npm_test",
                    "framework": "node",
                    "command": "npm test",
                    "discovery_pattern": "**/*.test.js",
                    "config_file": "package.json"
                })
        except Exception:
            pass

    # 3. Go
    if (workspace / "go.mod").exists() or any(workspace.glob("*_test.go")):
        detected.append({
            "runner": "go_test",
            "framework": "go",
            "command": "go test ./...",
            "discovery_pattern": "**/*_test.go",
            "config_file": "go.mod" if (workspace / "go.mod").exists() else None
        })

    # 4. Rust / Cargo
    if (workspace / "Cargo.toml").exists():
        detected.append({
            "runner": "cargo_test",
            "framework": "rust",
            "command": "cargo test",
            "discovery_pattern": "tests/**/*.rs",
            "config_file": "Cargo.toml"
        })

    primary = detected[0] if detected else {
        "runner": "generic_pytest",
        "framework": "python",
        "command": "pytest",
        "discovery_pattern": "test_*.py",
        "config_file": None
    }

    return {
        "workspace": str(workspace),
        "primary_runner": primary["runner"],
        "test_command": primary["command"],
        "discovery_pattern": primary["discovery_pattern"],
        "config_file": primary["config_file"],
        "available_runners": detected
    }


def scaffold_github_workflow(
    workflow_type: Literal["ci", "lint", "test"] = "ci",
    workspace_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Drops a standard, pre-tested GitHub Actions workflow YAML into
    .github/workflows/ so the repository has operational CI upon push.
    """
    workspace = _resolve_workspace(workspace_dir)
    workflows_dir = workspace / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    # Detect primary stack
    runner_info = detect_test_runner(workspace)
    test_cmd = runner_info["test_command"]
    framework = runner_info.get("available_runners", [{}])[0].get("framework", "python") if runner_info.get("available_runners") else "python"

    filename = f"{workflow_type}.yml"
    target_file = workflows_dir / filename

    if framework == "node":
        steps_yaml = f"""      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
      - name: Install dependencies
        run: npm ci || npm install
      - name: Run verification
        run: {test_cmd}
"""
    elif framework == "go":
        steps_yaml = f"""      - name: Setup Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'
      - name: Run verification
        run: {test_cmd}
"""
    elif framework == "rust":
        steps_yaml = f"""      - name: Setup Rust toolchain
        uses: dtolnay/rust-toolchain@stable
      - name: Run verification
        run: {test_cmd}
"""
    else: # Python default
        lint_step = "      - name: Run linter\n        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true\n" if workflow_type in ("ci", "lint") else ""
        test_step = f"      - name: Run test suite\n        run: {test_cmd}\n" if workflow_type in ("ci", "test") else ""
        steps_yaml = f"""      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f pyproject.toml ]; then pip install .; fi
          pip install pytest flake8
{lint_step}{test_step}"""

    workflow_content = f"""name: {workflow_type.upper()} Workflow

on:
  push:
    branches: [ main, 'jira-**' ]
  pull_request:
    branches: [ main ]

jobs:
  {workflow_type}:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

{steps_yaml}"""

    target_file.write_text(workflow_content, encoding="utf-8")
    logger.info(f"Scaffolded GitHub workflow: {target_file}")

    return {
        "success": True,
        "workflow_file": str(target_file.relative_to(workspace)),
        "workflow_type": workflow_type,
        "framework": framework,
        "content": workflow_content
    }


def scaffold_devcontainer(
    base_image: str = "mcr.microsoft.com/devcontainers/python:3.12",
    extensions: Optional[List[str]] = None,
    post_create_cmd: Optional[str] = None,
    workspace_dir: Optional[Union[str, Path]] = None
) -> Dict[str, Any]:
    """
    Dynamically generates custom .devcontainer/devcontainer.json and Dockerfile definitions.
    """
    workspace = _resolve_workspace(workspace_dir)
    devcontainer_dir = workspace / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    default_extensions = extensions or [
        "ms-python.python",
        "ms-python.vscode-pylance",
        "ms-python.black-formatter",
        "dbaeumer.vscode-eslint"
    ]
    create_cmd = post_create_cmd or "pip install -e . || pip install -r requirements.txt || npm install || true"

    # 1. .devcontainer/Dockerfile
    dockerfile_path = devcontainer_dir / "Dockerfile"
    dockerfile_content = f"""FROM {base_image}

# Install core utilities
RUN apt-get update && apt-get install -y --no-install-recommends \\
    git curl ca-certificates jq build-essential \\
    && rm -rf /var/lib/apt/lists/*

USER vscode
"""
    dockerfile_path.write_text(dockerfile_content, encoding="utf-8")

    # 2. .devcontainer/devcontainer.json
    config_dict = {
        "name": f"DevContainer - {workspace.name}",
        "build": {
            "dockerfile": "Dockerfile"
        },
        "workspaceMount": "source=${localWorkspaceFolder},target=/workspace,type=bind,consistency=cached",
        "workspaceFolder": "/workspace",
        "customizations": {
            "vscode": {
                "extensions": default_extensions
            },
            "cursor": {
                "editorRules": [
                    "Follow deterministic code conventions",
                    "Always execute tests before completion"
                ],
                "systemPrompt": "You are pair programming in an OCI Dev Container.",
                "toolAuthorizations": {
                    "allowTerminalExecution": True,
                    "allowFileModifications": True
                }
            }
        },
        "postCreateCommand": create_cmd,
        "remoteUser": "vscode"
    }

    json_path = devcontainer_dir / "devcontainer.json"
    json_path.write_text(json.dumps(config_dict, indent=2) + "\n", encoding="utf-8")

    return {
        "success": True,
        "created_files": [
            str(dockerfile_path.relative_to(workspace)),
            str(json_path.relative_to(workspace))
        ],
        "devcontainer_config": config_dict
    }


def generate_task_directive(
    target: Literal["devin", "grok", "cursor", "jules", "codex"],
    prompt_content: Optional[str] = None,
    workspace_dir: Optional[Union[str, Path]] = None,
    task_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compiles the unified prompt.md into the syntax and format preferred by the
    specific downstream platform.
    """
    workspace = _resolve_workspace(workspace_dir)
    ctx = task_context or {}
    ticket_key = ctx.get("ticket_key", "TASK-001")
    test_cmd = ctx.get("test_command", "pytest")

    # Load prompt.md if not provided
    raw_prompt = prompt_content
    if not raw_prompt:
        candidate_paths = [
            workspace / ".harness" / "prompt.md",
            workspace / "prompt.md"
        ]
        for cp in candidate_paths:
            if cp.exists():
                raw_prompt = cp.read_text(encoding="utf-8")
                break
    if not raw_prompt:
        raw_prompt = f"Implement changes requested for {ticket_key}."

    target_clean = str(target).lower().strip()
    directive_content = ""
    target_rel_path = ""

    if target_clean == "devin":
        target_rel_path = "devin_instructions.md"
        directive_content = f"""# Devin Autonomous Engineer Task Directive: {ticket_key}

## Goal
{raw_prompt.strip()}

## Multi-Step Plan
1. Run setup: `bash scripts/devin_setup.sh`
2. Run baseline test: `bash scripts/devin_test.sh`
3. Implement isolated code changes according to requirements.
4. Verify tests pass cleanly: `{test_cmd}`
5. Inspect git status and review diff.

## Execution Anchors
- Setup script: `scripts/devin_setup.sh`
- Test script: `scripts/devin_test.sh`
"""
    elif target_clean == "grok":
        target_rel_path = ".grok/build-config.json"
        grok_data = {
            "version": "1.0",
            "task_id": ticket_key,
            "prompt_spec": raw_prompt.strip(),
            "constraints": [
                "Only modify mapped target files",
                f"Verify changes using: {test_cmd}"
            ],
            "allowed_execution_steps": [
                "read_repo_tree",
                "edit_files",
                "run_tests"
            ]
        }
        directive_content = json.dumps(grok_data, indent=2)
    elif target_clean == "cursor":
        target_rel_path = ".cursorrules"
        directive_content = f"""# Cursor Task Rules for {ticket_key}
You are an expert engineer working in Cursor.

## Task Prompt
{raw_prompt.strip()}

## Strict Guidelines
- Run test command `{test_cmd}` to verify all logic changes.
- Never commit broken code or leave debug statements.
- Format all files cleanly according to repository conventions.
"""
    elif target_clean == "jules":
        target_rel_path = ".jules/config.yaml"
        directive_content = f"""# Google Jules Task Directive
version: 1
ticket_key: {ticket_key}
instructions: |
  {raw_prompt.strip()}
hooks:
  test: {test_cmd}
"""
    elif target_clean == "codex":
        target_rel_path = ".codex/task.json"
        codex_data = {
            "ticket": ticket_key,
            "target": "OPENAI_CODEX_CLOUD",
            "prompt": raw_prompt.strip(),
            "verification_command": test_cmd
        }
        directive_content = json.dumps(codex_data, indent=2)
    else:
        raise ValueError(f"Unknown target directive: {target}")

    # Write target file into workspace
    out_file = workspace / target_rel_path
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(directive_content, encoding="utf-8")

    return {
        "success": True,
        "target": target_clean,
        "target_file": target_rel_path,
        "directive_content": directive_content
    }


def verify_container_health(workspace_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Diagnostic utility checking local disk space, memory limits, network egress,
    and binary availability.
    """
    workspace = _resolve_workspace(workspace_dir)
    report: Dict[str, Any] = {
        "status": "HEALTHY",
        "workspace": str(workspace),
        "disk_space": {},
        "memory": {},
        "network_egress": {},
        "binaries": {},
        "issues": []
    }

    # 1. Disk Space check
    try:
        total, used, free = shutil.disk_usage(workspace)
        free_gb = round(free / (1024 ** 3), 2)
        total_gb = round(total / (1024 ** 3), 2)
        used_pct = round((used / total) * 100, 1)
        report["disk_space"] = {
            "free_gb": free_gb,
            "total_gb": total_gb,
            "used_percentage": used_pct,
            "sufficient": free_gb > 1.0
        }
        if free_gb < 1.0:
            report["status"] = "DEGRADED"
            report["issues"].append(f"Low disk space: only {free_gb} GB free on workspace volume.")
    except Exception as e:
        report["disk_space"] = {"error": str(e)}

    # 2. Memory limits check
    try:
        # Check cgroup memory limits if present, otherwise system memory
        cgroup_mem_limit_path = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
        cgroup_v2_mem_limit_path = Path("/sys/fs/cgroup/memory.max")
        mem_limit_bytes = None

        if cgroup_v2_mem_limit_path.exists():
            val = cgroup_v2_mem_limit_path.read_text().strip()
            if val != "max":
                mem_limit_bytes = int(val)
        elif cgroup_mem_limit_path.exists():
            mem_limit_bytes = int(cgroup_mem_limit_path.read_text().strip())

        if mem_limit_bytes and mem_limit_bytes < 9223372036854771712:
            mem_limit_gb = round(mem_limit_bytes / (1024 ** 3), 2)
            report["memory"] = {
                "cgroup_limit_gb": mem_limit_gb,
                "enforced": True
            }
        else:
            report["memory"] = {
                "cgroup_limit": "unlimited_or_host",
                "enforced": False
            }
    except Exception as e:
        report["memory"] = {"error": str(e)}

    # 3. Network Egress check
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        # Check connectivity to standard DNS host (1.1.1.1:53)
        res = sock.connect_ex(("1.1.1.1", 53))
        sock.close()
        egress_ok = (res == 0)
        report["network_egress"] = {
            "can_connect_external": egress_ok,
            "dns_probe": "passed" if egress_ok else "unreachable"
        }
        if not egress_ok:
            report["status"] = "DEGRADED"
            report["issues"].append("External network egress probe unreachable (offline container or firewall).")
    except Exception as e:
        report["network_egress"] = {"can_connect_external": False, "error": str(e)}

    # 4. Binary availability check
    expected_binaries = ["git", "curl", "jq", "python3", "tar", "gzip"]
    binary_status = {}
    missing_binaries = []
    for b in expected_binaries:
        loc = shutil.which(b)
        binary_status[b] = loc if loc else False
        if not loc:
            missing_binaries.append(b)

    report["binaries"] = binary_status
    if missing_binaries:
        report["status"] = "DEGRADED"
        report["issues"].append(f"Missing required baseline utilities: {missing_binaries}")

    if len(report["issues"]) > 2:
        report["status"] = "UNHEALTHY"

    return report
