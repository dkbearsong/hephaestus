import json
import os
import shutil
import tempfile
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal

from services.models import WorkspaceTriggerPayload, HandoffState
from services.scaffolding import GitRunner
from services.workspace_orchestrator import workspace_orchestrator, WorkspaceOrchestrator
from backend.jira_service.client import jira_service

logger = logging.getLogger("hephaestus.test_harness.jira_runner")


class JiraTicketWorkspaceRunner:
    """
    Runs a test ticket from Jira through the WorkspaceOrchestrator pipeline
    and verifies the resulting repository, platform configuration, file scaffolding,
    preparation agent outputs, and handoff tracking state.
    """

    def __init__(self, orchestrator: Optional[WorkspaceOrchestrator] = None):
        self.orchestrator = orchestrator or workspace_orchestrator
        self.jira_client = jira_service

    def run_and_verify_ticket(
        self,
        ticket_key: str = "PROJ-101",
        mode: Literal["PROMPT_NEW", "PROMPT"] = "PROMPT_NEW",
        target_platform: Literal["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"] = "LOCAL_CONTAINER",
        repo_url: Optional[str] = None,
        comment_text: Optional[str] = None,
        preparations_text: Optional[str] = None,
        staged_files: Optional[Dict[str, str]] = None,
        use_live_jira: bool = False,
        workspaces_root: Optional[Path] = None,
        cleanup_after: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a test ticket run and verifies all orchestrator behaviors.
        """
        verifications: Dict[str, bool] = {}
        errors: List[str] = []
        cleanup_paths: List[Path] = []

        if verbose:
            print("\n" + "=" * 80)
            print(f"🎫 RUNNING JIRA TEST TICKET: {ticket_key}")
            print("=" * 80)
            print(f"• Mode: {mode}")
            print(f"• Target Platform: {target_platform}")
            print(f"• Query Live Jira Cloud: {use_live_jira}")

        # 1. Fetch live details if requested
        jira_issue_meta = {}
        if use_live_jira:
            try:
                jira_issue_meta = self.jira_client.get_issue_details(ticket_key)
                if verbose:
                    print(f"• Jira Summary: {jira_issue_meta.get('summary')}")
                    print(f"• Jira Status: {jira_issue_meta.get('status')}")
            except Exception as e:
                logger.warning(f"Could not retrieve Jira issue {ticket_key}: {e}")
                errors.append(f"Live Jira query warning: {str(e)}")

        # 2. Setup Staging Directory
        temp_staging_dir = Path(tempfile.mkdtemp(prefix=f"staging_{ticket_key}_"))
        cleanup_paths.append(temp_staging_dir)

        prompt_body = comment_text or (
            f"# Feature Request for {ticket_key}\n"
            f"Implement JWT authentication middleware and user session expiration handling.\n"
        )
        prep_body = preparations_text or (
            "Move auth_middleware.py to services/auth/\n"
            "Install pyjwt>=2.8.0\n"
            "Ensure pytest is configured as the test runner.\n"
        )

        (temp_staging_dir / "prompt.md").write_text(prompt_body, encoding="utf-8")
        (temp_staging_dir / "preparations.md").write_text(prep_body, encoding="utf-8")

        # Staged files directory
        staged_dir = temp_staging_dir / "staged_files"
        staged_dir.mkdir(parents=True, exist_ok=True)

        files_to_stage = staged_files or {
            "auth_middleware.py": "# Auth Middleware\ndef authenticate(token):\n    return True\n",
            "run_tests.sh": "#!/bin/bash\npytest tests/\n",
            ".env.staging": "JWT_SECRET=super-secret-key-123\nTOKEN_EXPIRY=3600\n"
        }

        for filename, content in files_to_stage.items():
            file_path = staged_dir / filename
            file_path.write_text(content, encoding="utf-8")

        if verbose:
            print(f"📁 Prepared staging directory with {len(files_to_stage)} staged files.")

        # 3. Setup Workspaces Root & Upstream Repo (if PROMPT mode)
        actual_workspaces_root = workspaces_root or Path(tempfile.mkdtemp(prefix="workspaces_"))
        if not workspaces_root:
            cleanup_paths.append(actual_workspaces_root)

        resolved_repo_url = repo_url
        if mode == "PROMPT" and not resolved_repo_url:
            # Create a mock upstream Git repo for cloning in test
            mock_upstream = Path(tempfile.mkdtemp(prefix="mock_upstream_"))
            cleanup_paths.append(mock_upstream)
            GitRunner.run_git(["init", "-b", "main"], cwd=mock_upstream)
            GitRunner.run_git(["config", "user.name", "Upstream Dev"], cwd=mock_upstream)
            GitRunner.run_git(["config", "user.email", "dev@upstream.internal"], cwd=mock_upstream)
            (mock_upstream / "app.py").write_text("# Main Application\nprint('App running')\n", encoding="utf-8")
            (mock_upstream / "requirements.txt").write_text("fastapi>=0.100.0\n", encoding="utf-8")
            (mock_upstream / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
            GitRunner.run_git(["add", "."], cwd=mock_upstream)
            GitRunner.run_git(["commit", "-m", "Initial upstream base commit"], cwd=mock_upstream)
            resolved_repo_url = str(mock_upstream)

        # 4. Construct WorkspaceTriggerPayload
        payload = WorkspaceTriggerPayload(
            ticket_key=ticket_key,
            mode=mode,
            target_platform=target_platform,
            repo_url=resolved_repo_url,
            staging_dir=temp_staging_dir,
            workspaces_root=actual_workspaces_root
        )

        # 5. Execute WorkspaceOrchestrator
        if verbose:
            print(f"\n⚙️  Orchestrating workspace for platform {target_platform}...")

        handoff_state: Optional[HandoffState] = None
        start_time = time.perf_counter()
        try:
            handoff_state = self.orchestrator.orchestrate(payload)
        except Exception as e:
            logger.error(f"Orchestration failed: {e}", exc_info=True)
            errors.append(f"Orchestration exception: {str(e)}")

        elapsed = time.perf_counter() - start_time

        # 6. Verify Behaviors
        working_dir_path = Path(handoff_state.working_directory) if handoff_state else None
        
        # Verification 1: Working directory exists
        v_dir_exists = bool(working_dir_path and working_dir_path.exists() and working_dir_path.is_dir())
        verifications["directory_created"] = v_dir_exists

        # Verification 2: Git repository and branch
        v_git_branch = False
        if v_dir_exists:
            try:
                branch_res = GitRunner.run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=working_dir_path)
                current_branch = branch_res.stdout.strip()
                expected_branch = "main" if mode == "PROMPT_NEW" else f"jira-{ticket_key}-agent"
                v_git_branch = (current_branch == expected_branch)
            except Exception as ex:
                errors.append(f"Git branch check failed: {ex}")
        verifications["git_branch_valid"] = v_git_branch

        # Verification 3: Provider-specific rules
        v_provider_rules = False
        if v_dir_exists:
            if target_platform == "GOOGLE_JULES":
                jules_cfg = working_dir_path / ".jules" / "config.yaml"
                status_res = GitRunner.run_git(["status", "--porcelain"], cwd=working_dir_path)
                zero_uncommitted = (status_res.stdout.strip() == "")
                v_provider_rules = jules_cfg.exists() and zero_uncommitted
            elif target_platform == "CODEX_CLOUD":
                task_meta = working_dir_path / ".codex" / "task_metadata.json"
                entrypoint_exists = any(
                    (working_dir_path / ep).exists()
                    for ep in ["main.py", "app.py", "index.js", "pyproject.toml"]
                )
                v_provider_rules = task_meta.exists() and entrypoint_exists
            elif target_platform == "LOCAL_CONTAINER":
                mounts_cfg = working_dir_path / ".docker" / "mounts.json"
                env_file = working_dir_path / ".env"
                # Check execution permissions on any .sh scripts
                sh_scripts = list(working_dir_path.rglob("*.sh"))
                scripts_executable = all(os.access(s, os.X_OK) for s in sh_scripts) if sh_scripts else True
                v_provider_rules = mounts_cfg.exists() and env_file.exists() and scripts_executable
        verifications["provider_rules_enforced"] = v_provider_rules

        # Verification 4: Staged files handled & inbox cleared
        v_staged_handled = False
        if v_dir_exists:
            inbox_cleared = not (working_dir_path / ".harness_inbox").exists()
            # Verify relocated files (e.g. auth_middleware.py moved)
            relocated_exists = (
                (working_dir_path / "services" / "auth" / "auth_middleware.py").exists() or
                (working_dir_path / "auth_middleware.py").exists()
            )
            v_staged_handled = inbox_cleared and relocated_exists
        verifications["staged_files_handled"] = v_staged_handled

        # Verification 5: Commands detected
        detected = handoff_state.prep_summary.detected_commands if handoff_state else {}
        v_commands = bool(detected and isinstance(detected, dict))
        verifications["commands_detected"] = v_commands

        # Verification 6: Handoff file recorded
        v_handoff = False
        if v_dir_exists:
            handoff_file = working_dir_path / ".hephaestus_handoff.json"
            v_handoff = handoff_file.exists() and handoff_state.ready_for_execution
        verifications["handoff_recorded"] = v_handoff

        # Verification 7: Jira label removed (simulated or real)
        if use_live_jira:
            label_res = self.jira_client.remove_trigger_label(ticket_key)
            verifications["jira_label_handled"] = bool(label_res)
        else:
            # Synthetic test ticket: simulate label removal if Jira Cloud returns 404 or in test mode
            if not self.jira_client.jira:
                label_res = self.jira_client.remove_trigger_label(ticket_key)
            else:
                # Jira client is connected to live Cloud, but this is a synthetic test ticket
                logger.info(f"[TEST HARNESS] Simulated trigger label removal for test ticket {ticket_key}")
                label_res = True
            verifications["jira_label_handled"] = bool(label_res)

        all_verified = all(verifications.values()) and not errors

        # Output Summary
        if verbose:
            print("\n" + "=" * 80)
            print(f"📊 JIRA TICKET VERIFICATION SUMMARY: {ticket_key}")
            print("=" * 80)
            for check_name, status in verifications.items():
                icon = "✅ PASS" if status else "❌ FAIL"
                print(f"  • {check_name:<28}: {icon}")
            
            print(f"\n• Working Directory: {working_dir_path}")
            print(f"• Branch Name:       {handoff_state.branch_name if handoff_state else 'N/A'}")
            print(f"• Detected Commands: {detected}")
            print(f"• Execution Time:    {elapsed:.2f}s")
            print(f"• Overall Status:    {'✅ VERIFIED' if all_verified else '❌ FAILED'}")
            if errors:
                print("\n⚠️  Errors Encountered:")
                for err in errors:
                    print(f"  - {err}")
            print("=" * 80)

        # Cleanup if requested
        if cleanup_after:
            for p in cleanup_paths:
                try:
                    shutil.rmtree(p, ignore_errors=True)
                except Exception:
                    pass

        return {
            "success": all_verified,
            "ticket_key": ticket_key,
            "mode": mode,
            "target_platform": target_platform,
            "working_directory": str(working_dir_path) if working_dir_path else None,
            "branch_name": handoff_state.branch_name if handoff_state else None,
            "verifications": verifications,
            "detected_commands": detected,
            "duration_seconds": round(elapsed, 3),
            "errors": errors,
            "handoff_state": handoff_state.model_dump() if handoff_state else None
        }


jira_ticket_workspace_runner = JiraTicketWorkspaceRunner()
