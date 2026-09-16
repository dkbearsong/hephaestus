import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from services.agents.registry import agent_registry, AgentSpec
from services.sandbox.docker_runner import local_docker_runner, LocalDockerRunner
from services.scaffolding import GitRunner
from backend.db.service import async_session_factory
from backend.db.models import Run, RunEvent
from backend.jira_service.client import jira_service

logger = logging.getLogger("hephaestus.lifecycle")


class SandboxLifecycleManager:
    """
    Coordinates container execution, log persistence, git finalization, and status updates.
    """

    def __init__(self, docker_runner: Optional[LocalDockerRunner] = None):
        self.runner = docker_runner or local_docker_runner

    async def execute_run_lifecycle(
        self,
        run_id: str,
        ticket_key: str,
        workspace_dir: Path,
        agent_name: str = "antigravity"
    ) -> Dict[str, Any]:
        """
        Executes full agent lifecycle inside sandbox:
        1. Boot container with target AgentSpec.
        2. Execute agent against /workspace/prompt.md and /workspace/task_context.md.
        3. Await exit code:
           - On Exit Code 0: Commit uncommitted git changes ("feat: completed by agent ${agent_name}"),
             push branch ("jira-${ticket_key}-agent"), set status="COMPLETED", trigger PR creation.
           - On Non-Zero Exit: Set status="FAILED", persist stderr output, notify Jira.
        4. Tear down container.
        """
        resolved_workspace = Path(workspace_dir).resolve()
        spec: AgentSpec = agent_registry.get(agent_name)
        branch_name = f"jira-{ticket_key.lower()}-agent"

        # Update run status to CODING
        if async_session_factory:
            async with async_session_factory() as session:
                run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                run = await session.get(Run, run_uuid)
                if run:
                    run.status = "CODING"
                    run.branch_name = branch_name
                    await session.commit()

        # Execute container
        exec_res = await self.runner.run_container(
            run_id=run_id,
            workspace_dir=resolved_workspace,
            agent_spec=spec
        )

        exit_code = exec_res.get("exit_code", 1)

        if exit_code == 0:
            logger.info(f"[Lifecycle] Run {run_id} container exited with 0. Finalizing Git operations...")
            try:
                # Inspect git changes
                status_res = GitRunner.run_git(["status", "--porcelain"], cwd=resolved_workspace, stream_logs=False)
                if status_res.stdout.strip():
                    GitRunner.run_git(["add", "."], cwd=resolved_workspace)
                    GitRunner.run_git(
                        ["commit", "-m", f"feat: completed by agent {agent_name}"],
                        cwd=resolved_workspace
                    )

                # Push branch
                if GitRunner.remote_exists(resolved_workspace, "origin"):
                    try:
                        GitRunner.push_branch(resolved_workspace, branch_name, remote="origin", set_upstream=True)
                    except Exception as push_err:
                        logger.warning(f"[Lifecycle] Failed pushing branch {branch_name}: {push_err}")

                # Update runs status = COMPLETED
                if async_session_factory:
                    async with async_session_factory() as session:
                        run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                        run = await session.get(Run, run_uuid)
                        if run:
                            run.status = "COMPLETED"
                            await session.commit()

                # Notify Jira
                jira_service.add_comment(
                    ticket_key,
                    f"✅ **Agent {agent_name} Execution Completed Successfully**\nBranch: `{branch_name}`"
                )

                return {
                    "success": True,
                    "status": "COMPLETED",
                    "branch_name": branch_name,
                    "agent_name": agent_name
                }

            except Exception as git_err:
                logger.error(f"[Lifecycle] Git finalization error for run {run_id}: {git_err}")
                if async_session_factory:
                    async with async_session_factory() as session:
                        run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                        run = await session.get(Run, run_uuid)
                        if run:
                            run.status = "FAILED"
                            run.error_message = f"Git finalization failed: {git_err}"
                            await session.commit()
                return {"success": False, "status": "FAILED", "error": str(git_err)}

        else:
            stderr_msg = exec_res.get("error") or f"Container exited with code {exit_code}"
            logger.error(f"[Lifecycle] Run {run_id} failed with exit code {exit_code}: {stderr_msg}")

            if async_session_factory:
                async with async_session_factory() as session:
                    run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                    run = await session.get(Run, run_uuid)
                    if run:
                        run.status = "FAILED"
                        run.error_message = stderr_msg
                        await session.commit()

            jira_service.add_comment(
                ticket_key,
                f"❌ **Agent {agent_name} Execution Failed**\nExit Code: {exit_code}\nError: {stderr_msg}"
            )

            return {
                "success": False,
                "status": "FAILED",
                "exit_code": exit_code,
                "error": stderr_msg
            }


sandbox_lifecycle = SandboxLifecycleManager()
