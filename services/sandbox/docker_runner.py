import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from services.agents.registry import AgentSpec, agent_registry
from services.sandbox.guardrail import sandbox_guardrail
from backend.db.service import async_session_factory
from backend.db.models import Run, RunEvent

logger = logging.getLogger("hephaestus.docker_runner")

try:
    import docker
except ImportError:
    docker = None


class LocalDockerRunner:
    """
    Spawns an ephemeral, resource-constrained autonomous Docker container for the workspace.
    Streams execution logs into PostgreSQL telemetry layer and WebSocket/SSE pipeline.
    """

    def __init__(self):
        self.docker_client = None
        if docker:
            try:
                self.docker_client = docker.from_env()
            except Exception as e:
                logger.warning(f"[LocalDockerRunner] Docker SDK initialized without active daemon: {e}")

    async def log_event(
        self,
        run_id: str,
        event_type: str,
        payload: Any,
        level: str = "INFO"
    ):
        """
        Persists container log or event chunk into run_events table.
        """
        if not async_session_factory:
            return

        try:
            async with async_session_factory() as session:
                run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
                event = RunEvent(
                    run_id=run_uuid,
                    event_type=event_type,
                    level=level,
                    payload=payload if isinstance(payload, dict) else {"log": str(payload)}
                )
                session.add(event)
                await session.commit()
        except Exception as e:
            logger.error(f"[LocalDockerRunner] Failed to persist log event for run {run_id}: {e}")

    async def stream_container_logs(self, container, run_id: str):
        """
        Asynchronously reads container output stream and writes to run_events (DOCKER_STDOUT).
        """
        loop = asyncio.get_running_loop()

        def _get_log_stream():
            return container.logs(stream=True, follow=True)

        try:
            log_stream = await loop.run_in_executor(None, _get_log_stream)
            for chunk in log_stream:
                if chunk:
                    decoded = chunk.decode("utf-8", errors="replace").strip()
                    if decoded:
                        await self.log_event(run_id, "DOCKER_STDOUT", {"log": decoded})
        except Exception as e:
            logger.debug(f"[LocalDockerRunner] Log streaming ended for run {run_id}: {e}")

    async def run_container(
        self,
        run_id: str,
        workspace_dir: Path,
        agent_spec: AgentSpec,
        prompt_file_name: str = "prompt.md",
        task_context_file_name: str = "task_context.md"
    ) -> Dict[str, Any]:
        """
        Boots ephemeral container with resource caps and mounts workspace.
        """
        resolved_workspace = Path(workspace_dir).resolve()
        resolved_workspace.mkdir(parents=True, exist_ok=True)
        prompt_path = resolved_workspace / prompt_file_name

        # Ensure task_context.md exists in workspace
        task_context_path = resolved_workspace / task_context_file_name
        if not task_context_path.exists():
            task_context_path.write_text(f"# Task Context\nRun ID: {run_id}\nAgent: {agent_spec.name}\n", encoding="utf-8")

        cmd = agent_spec.entrypoint_cmd(resolved_workspace, str(prompt_path))

        env = {
            "RUN_ID": str(run_id),
            "WORKSPACE_DIR": "/workspace",
            "PYTHONUNBUFFERED": "1"
        }
        env.update(agent_spec.env_overrides)

        labels = {
            "harness_run_id": str(run_id),
            "agent_name": agent_spec.name,
            "managed_by": "hephaestus"
        }

        # Mounts: strictly mount {workspace_dir}:/workspace:rw
        volumes = {
            str(resolved_workspace): {
                "bind": "/workspace",
                "mode": "rw"
            }
        }

        logger.info(
            f"[LocalDockerRunner] Launching container for run {run_id} using image '{agent_spec.docker_image}' "
            f"with cmd: {cmd}"
        )

        if not self.docker_client:
            logger.warning("[LocalDockerRunner] Docker client unavailable. Simulating container execution.")
            await self.log_event(
                run_id,
                "DOCKER_STDOUT",
                {"log": f"[Simulated Container] Running {agent_spec.name} against /workspace/{prompt_file_name}"}
            )
            await asyncio.sleep(0.5)
            return {"exit_code": 0, "simulated": True, "container_id": "simulated_container_id"}

        loop = asyncio.get_running_loop()

        def _create_and_start():
            container = self.docker_client.containers.create(
                image=agent_spec.docker_image,
                command=cmd,
                environment=env,
                volumes=volumes,
                user="1000:1000",
                nano_cpus=2000000000, # 2 cores limit
                mem_limit="4g",       # 4GB RAM limit
                labels=labels,
                working_dir="/workspace",
                detach=True
            )
            container.start()
            return container

        container = None
        try:
            container = await loop.run_in_executor(None, _create_and_start)
            await self.log_event(run_id, "DOCKER_STDOUT", {"log": f"Container started: {container.id[:12]}"})

            # Stream logs in background task
            stream_task = asyncio.create_task(self.stream_container_logs(container, run_id))

            # Wait for container exit
            def _wait():
                return container.wait()

            result = await loop.run_in_executor(None, _wait)
            exit_code = result.get("StatusCode", 0)

            await stream_task

            return {
                "exit_code": exit_code,
                "container_id": container.id,
                "simulated": False
            }

        except Exception as e:
            logger.error(f"[LocalDockerRunner] Error running container for {run_id}: {e}")
            await self.log_event(run_id, "DOCKER_STDOUT", {"log": f"Container execution error: {e}"}, level="ERROR")
            return {
                "exit_code": 1,
                "error": str(e),
                "simulated": False
            }
        finally:
            if container:
                def _cleanup():
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
                await loop.run_in_executor(None, _cleanup)

    async def kill_container(self, run_id: str) -> bool:
        """
        Forces container termination for a given run_id using harness_run_id label.
        """
        if not self.docker_client:
            logger.info(f"[LocalDockerRunner] Docker client unavailable. Simulating container kill for run {run_id}")
            return True

        loop = asyncio.get_running_loop()

        def _kill():
            containers = self.docker_client.containers.list(
                filters={"label": f"harness_run_id={run_id}"}
            )
            for c in containers:
                try:
                    c.kill()
                    c.remove(force=True)
                except Exception as e:
                    logger.warning(f"Error killing container {c.id}: {e}")
            return len(containers) > 0

        return await loop.run_in_executor(None, _kill)


local_docker_runner = LocalDockerRunner()
