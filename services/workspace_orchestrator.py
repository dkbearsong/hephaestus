import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from services.models import (
    WorkspaceTriggerPayload,
    PrepSummary,
    ProviderConfig,
    HandoffState,
    HarnessManifest,
    RepoCoordinates,
    PromptLocation
)
from services.scaffolding import ScaffoldingEngine, scaffolding_engine, GitRunner
from services.provider_prep import ProviderPrepEngine, provider_prep_engine
from services.prep_agent import PreparationAgent, prep_agent
from services.events import event_bus, WORKSPACE_READY_FOR_AGENT, WORKSPACE_BLOCKED
from services.github_service import GitHubService, github_service
from backend.jira_service.client import jira_service

logger = logging.getLogger("hephaestus.services.workspace_orchestrator")


class WorkspaceOrchestrator:
    """
    Master WorkspaceOrchestrator service.
    Bridges the completed parser step (prompt.md, preparations.md, staged_files)
    to downstream coding agent execution platforms (Google Jules, Codex Cloud, Local Container).
    """

    def __init__(
        self,
        scaffolding: Optional[ScaffoldingEngine] = None,
        provider_prep: Optional[ProviderPrepEngine] = None,
        agent: Optional[PreparationAgent] = None,
        github: Optional[GitHubService] = None
    ):
        self.scaffolding = scaffolding or scaffolding_engine
        self.provider_prep = provider_prep or provider_prep_engine
        self.agent = agent or prep_agent
        self.github = github or github_service

    def orchestrate(self, payload: WorkspaceTriggerPayload) -> HandoffState:
        """
        Executes the full workspace orchestration pipeline:
        1. Validates inputs and staging paths.
        2. Scaffolds working directory and Git repository.
        3. Applies dynamic provider preparation and merges platform constraints with preparations.md.
        4. Dispatches Preparation Agent to organize files and verify commands without writing feature code.
        5. Persists handoff state into workspace and returns HandoffState.
        """
        logger.info(
            f"[WorkspaceOrchestrator] Starting orchestration for ticket {payload.ticket_key} "
            f"(Mode: {payload.mode}, Target: {payload.target_platform})"
        )

        # 1. Inspect Staging Directory
        staging_dir = Path(payload.staging_dir)
        prompt_md_path = staging_dir / "prompt.md"
        prep_md_path = staging_dir / "preparations.md"

        preparations_content = ""
        if prep_md_path.exists():
            preparations_content = prep_md_path.read_text(encoding="utf-8")

        # 2. Scaffolding Phase
        scaffold_res = self.scaffolding.setup_workspace(payload)
        working_dir: Path = scaffold_res["working_directory"]
        branch_name: str = scaffold_res["branch_name"]

        # 3. Provider Preparation Phase
        provider_cfg: ProviderConfig = self.provider_prep.prepare(
            working_dir=working_dir,
            target_platform=payload.target_platform,
            staging_dir=staging_dir,
            ticket_key=payload.ticket_key
        )

        # Merge provider constraints with preparations.md
        merged_instructions = self.provider_prep.merge_instructions(
            platform_config=provider_cfg,
            preparations_content=preparations_content
        )

        # Save merged instructions into workspace for inspection / auditing
        audit_dir = working_dir / ".harness"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "merged_preparations.md").write_text(merged_instructions, encoding="utf-8")

        # 4. Preparation Agent Phase
        prep_summary: PrepSummary = self.agent.run(
            working_dir=working_dir,
            branch_name=branch_name,
            merged_instructions=merged_instructions,
            prompt_md_path=prompt_md_path
        )

        created_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 4.1. Handle BLOCKED Status
        if prep_summary.status == "BLOCKED":
            blocker_msg = prep_summary.blocker_reason or "Preparation phase failed requirements validation."
            logger.warning(
                f"[WorkspaceOrchestrator] Preparation BLOCKED for {payload.ticket_key}: {blocker_msg}"
            )

            # Emit WORKSPACE_BLOCKED event for Web UI and status logger
            event_bus.emit(WORKSPACE_BLOCKED, {
                "ticket_key": payload.ticket_key,
                "reason": blocker_msg,
                "working_directory": str(working_dir.resolve()),
                "prep_summary": prep_summary.model_dump()
            })

            # Add comment to Jira
            jira_service.add_comment(
                payload.ticket_key,
                f"🚫 **AI Preparation Blocked**: {blocker_msg}\n\nPlatform dispatch suspended. Please update ticket requirements."
            )

            handoff_file = working_dir / ".hephaestus_handoff.json"
            handoff_data = {
                "ticket_key": payload.ticket_key,
                "mode": payload.mode,
                "target_platform": payload.target_platform,
                "working_directory": str(working_dir.resolve()),
                "branch_name": branch_name,
                "ready_for_execution": False,
                "cloned": scaffold_res.get("cloned", True),
                "flags": payload.flags,
                "prep_summary": prep_summary.model_dump(),
                "provider_config": provider_cfg.model_dump(),
                "created_at": created_at_iso
            }
            handoff_file.write_text(json.dumps(handoff_data, indent=2), encoding="utf-8")

            return HandoffState(
                ticket_key=payload.ticket_key,
                mode=payload.mode,
                target_platform=payload.target_platform,
                working_directory=str(working_dir.resolve()),
                branch_name=branch_name,
                ready_for_execution=False,
                cloned=scaffold_res.get("cloned", True),
                flags=payload.flags,
                prep_summary=prep_summary,
                provider_config=provider_cfg,
                created_at=created_at_iso,
                handoff_file_path=str(handoff_file.resolve())
            )

        # 4.2. Handle READY Status: Commit all staged modifications
        try:
            GitRunner.run_git(["add", "."], cwd=working_dir)
            status_check = GitRunner.run_git(["status", "--porcelain"], cwd=working_dir, stream_logs=False)
            if status_check.stdout.strip():
                GitRunner.run_git(
                    ["commit", "-m", f"chore(harness): initialize workspace for {payload.ticket_key}"],
                    cwd=working_dir
                )
        except Exception as e:
            logger.warning(f"Failed to commit staged modifications: {e}")

        # 4.3. GitHub Synchronization
        remote_url = payload.repo_url
        if payload.mode == "PROMPT_NEW":
            try:
                repo_info = self.github.create_remote_repository(
                    repo_name=payload.ticket_key.lower()
                )
                remote_url = repo_info.get("clone_url") or remote_url
                if remote_url:
                    GitRunner.set_remote_origin(working_dir, remote_url)
                    try:
                        GitRunner.push_branch(working_dir, "main", remote="origin", set_upstream=True)
                    except Exception as push_err:
                        logger.warning(f"Could not push to remote main (offline/simulated): {push_err}")
            except Exception as gh_err:
                logger.warning(f"GitHub remote creation for PROMPT_NEW encountered: {gh_err}")

        elif payload.mode == "PROMPT":
            # If origin exists, push tracking branch
            if GitRunner.remote_exists(working_dir, "origin"):
                try:
                    GitRunner.push_branch(working_dir, branch_name, remote="origin", set_upstream=True)
                except Exception as push_err:
                    logger.warning(f"Could not push tracking branch {branch_name} (offline/simulated): {push_err}")

        # 4.4. Standardized harness_manifest.json in workspace root
        commit_sha = None
        try:
            commit_sha = GitRunner.get_current_commit_sha(working_dir)
        except Exception:
            pass

        manifest = HarnessManifest(
            ticket_key=payload.ticket_key,
            mode=payload.mode,
            target_platform=payload.target_platform,
            repo_coordinates=RepoCoordinates(
                repo_url=remote_url,
                branch=branch_name,
                commit_sha=commit_sha
            ),
            prompt_location=PromptLocation(
                prompt_file=str(prompt_md_path.resolve()) if prompt_md_path.exists() else str(prompt_md_path),
                preparations_file=str(prep_md_path.resolve()) if prep_md_path.exists() else None
            ),
            detected_commands=prep_summary.detected_commands,
            created_at=created_at_iso
        )

        manifest_file = working_dir / "harness_manifest.json"
        manifest_file.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")

        # 4.5. Emit WORKSPACE_READY_FOR_AGENT Event
        event_bus.emit(WORKSPACE_READY_FOR_AGENT, {
            "ticket_key": payload.ticket_key,
            "manifest_path": str(manifest_file.resolve()),
            "manifest": manifest.model_dump(),
            "branch_name": branch_name,
            "working_directory": str(working_dir.resolve())
        })

        # 5. Handoff State Tracking (.hephaestus_handoff.json)
        handoff_file = working_dir / ".hephaestus_handoff.json"
        handoff_data = {
            "ticket_key": payload.ticket_key,
            "mode": payload.mode,
            "target_platform": payload.target_platform,
            "working_directory": str(working_dir.resolve()),
            "branch_name": branch_name,
            "ready_for_execution": True,
            "cloned": scaffold_res.get("cloned", True),
            "flags": payload.flags,
            "prep_summary": prep_summary.model_dump(),
            "provider_config": provider_cfg.model_dump(),
            "created_at": created_at_iso,
            "manifest_path": str(manifest_file.resolve())
        }
        handoff_file.write_text(json.dumps(handoff_data, indent=2), encoding="utf-8")

        handoff_state = HandoffState(
            ticket_key=payload.ticket_key,
            mode=payload.mode,
            target_platform=payload.target_platform,
            working_directory=str(working_dir.resolve()),
            branch_name=branch_name,
            ready_for_execution=True,
            cloned=scaffold_res.get("cloned", True),
            flags=payload.flags,
            prep_summary=prep_summary,
            provider_config=provider_cfg,
            created_at=created_at_iso,
            handoff_file_path=str(handoff_file.resolve()),
            manifest_path=str(manifest_file.resolve())
        )

        if payload.target_platform == "GOOGLE_JULES":
            try:
                GitRunner.run_git(["add", "."], cwd=working_dir)
                status_check = GitRunner.run_git(["status", "--porcelain"], cwd=working_dir)
                if status_check.stdout.strip():
                    GitRunner.run_git(
                        ["commit", "-m", "Commit final manifest and handoff for Google Jules"],
                        cwd=working_dir
                    )
            except Exception as e:
                logger.warning(f"Final Jules commit encountered: {e}")

        logger.info(
            f"[WorkspaceOrchestrator] Completed orchestration for {payload.ticket_key}. "
            f"Ready: {handoff_state.ready_for_execution}, Branch: {branch_name}"
        )
        return handoff_state


workspace_orchestrator = WorkspaceOrchestrator()
