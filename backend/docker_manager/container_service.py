import os
import re
import io
import tarfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import docker
from docker.errors import NotFound, DockerException
from backend.config import preferences, ROOT_DIR

logger = logging.getLogger("hephaestus.docker")

class DockerContainerManager:
    def __init__(self):
        self.settings = preferences.docker
        self.client: Optional[docker.DockerClient] = None
        self._init_client()

    def _init_client(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Successfully connected to Docker Daemon.")
        except Exception as e:
            logger.warning("Docker Daemon not reachable (%s). Utilizing local filesystem simulation sandbox.", e)
            self.client = None

    def sanitize_name(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", name)

    def get_container_name(self, project_key: str, branch_name: str) -> str:
        return f"{self.settings.container_prefix}{self.sanitize_name(project_key)}_{self.sanitize_name(branch_name)}"

    def get_checkpoint_tag(self, project_key: str, branch_name: str) -> str:
        return f"{self.settings.checkpoint_image_prefix}{self.sanitize_name(project_key).lower()}-{self.sanitize_name(branch_name).lower()}"

    def ensure_branch_container(
        self,
        project_key: str,
        branch_name: str,
        repo_url: Optional[str] = None,
        base_image: Optional[str] = None,
        staged_files: Optional[List[Dict[str, Any]]] = None,
        is_new_project: bool = False
    ) -> Dict[str, Any]:
        """
        Checks for an existing Docker container for this project + branch.
        - If found: starts it (if stopped) and copies staged files into container.
        - If not found: pulls parent image, creates container, clones repo / inits git,
          creates branch, copies staged files, sets up venv, installs dependencies.
        """
        container_name = self.get_container_name(project_key, branch_name)
        checkpoint_tag = self.get_checkpoint_tag(project_key, branch_name)
        workspace_inside = self.settings.workspace_dir_inside_container

        # Local fallback simulation sandbox directory
        host_sandbox_dir = ROOT_DIR / "sandboxes" / container_name
        host_sandbox_dir.mkdir(parents=True, exist_ok=True)

        if not self.client:
            return self._simulate_ensure_container(
                container_name, checkpoint_tag, host_sandbox_dir, branch_name, staged_files, is_new_project
            )

        try:
            existing = self.client.containers.get(container_name)
            logger.info("Existing container found: %s (status: %s)", container_name, existing.status)
            if existing.status != "running":
                existing.start()
                logger.info("Started stopped container: %s", container_name)

            if staged_files:
                self._copy_staged_files_to_container(existing, staged_files, workspace_inside)

            return {
                "success": True,
                "container_id": existing.id,
                "container_name": container_name,
                "status": "resumed",
                "checkpoint_tag": checkpoint_tag,
                "workspace_path": workspace_inside
            }
        except NotFound:
            logger.info("Container %s does not exist. Initializing new branch container...", container_name)
            return self._create_new_branch_container(
                container_name, checkpoint_tag, base_image or self.settings.default_base_image,
                project_key, branch_name, repo_url, staged_files, is_new_project
            )
        except Exception as e:
            logger.error("Error inspecting container %s: %s", container_name, e)
            return {"success": False, "error": str(e)}

    def _create_new_branch_container(
        self,
        container_name: str,
        checkpoint_tag: str,
        image_name: str,
        project_key: str,
        branch_name: str,
        repo_url: Optional[str],
        staged_files: Optional[List[Dict[str, Any]]],
        is_new_project: bool
    ) -> Dict[str, Any]:
        workspace_inside = self.settings.workspace_dir_inside_container
        try:
            # Check if a previous checkpoint image exists first
            use_image = image_name
            try:
                self.client.images.get(checkpoint_tag)
                use_image = checkpoint_tag
                logger.info("Reusing existing checkpoint image: %s", checkpoint_tag)
            except NotFound:
                pass

            container = self.client.containers.run(
                use_image,
                name=container_name,
                command="tail -f /dev/null", # Keep container alive
                detach=True,
                working_dir=workspace_inside,
                environment={"PROJECT_KEY": project_key, "BRANCH_NAME": branch_name}
            )

            # Inside container initialization
            if is_new_project:
                logger.info("Initializing brand new project inside container...")
                container.exec_run(f"mkdir -p {workspace_inside}")
                container.exec_run(f"git init {workspace_inside}")
                container.exec_run(f"python -m venv {workspace_inside}/.venv")
            else:
                if repo_url and use_image == image_name:
                    logger.info("Cloning repository %s into container...", repo_url)
                    clone_res = container.exec_run(f"git clone {repo_url} {workspace_inside}")
                    if clone_res.exit_code != 0:
                        container.exec_run(f"git init {workspace_inside}")
                
                # Checkout branch
                container.exec_run(f"git checkout -B {branch_name}", workdir=workspace_inside)
                # Initialize venv inside
                container.exec_run(f"python -m venv {workspace_inside}/.venv")
                # Install dependencies if requirements.txt exists
                container.exec_run(f"{workspace_inside}/.venv/bin/pip install --upgrade pip", workdir=workspace_inside)
                container.exec_run(f"bash -c '[ -f requirements.txt ] && {workspace_inside}/.venv/bin/pip install -r requirements.txt || true'", workdir=workspace_inside)

            # Copy staged files
            if staged_files:
                self._copy_staged_files_to_container(container, staged_files, workspace_inside)

            return {
                "success": True,
                "container_id": container.id,
                "container_name": container_name,
                "status": "created",
                "checkpoint_tag": checkpoint_tag,
                "workspace_path": workspace_inside
            }
        except Exception as e:
            logger.error("Failed to create branch container %s: %s", container_name, e)
            return {"success": False, "error": str(e)}

    def _copy_staged_files_to_container(self, container, staged_manifest: List[Dict[str, Any]], workspace: str):
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            for item in staged_manifest:
                staged_path = Path(item["staged_path"])
                if staged_path.exists():
                    arcname = f"staged_files/{staged_path.name}"
                    tar.add(str(staged_path), arcname=arcname)
        tar_stream.seek(0)
        try:
            container.put_archive(workspace, tar_stream.read())
            logger.info("Injected %d staged files into container workspace %s", len(staged_manifest), workspace)
        except Exception as e:
            logger.error("Error copying staged files into container: %s", e)

    def spin_down_and_checkpoint(self, container_name: str, checkpoint_tag: str) -> Dict[str, Any]:
        """
        Creates a checkpoint image of the current state and spins down (stops) the container.
        """
        if not self.client:
            logger.info("[MOCK] Checkpointed container %s to %s and spun down.", container_name, checkpoint_tag)
            return {"success": True, "status": "checkpointed"}

        try:
            container = self.client.containers.get(container_name)
            # Commit checkpoint image
            container.commit(repository=checkpoint_tag)
            logger.info("Committed container checkpoint image: %s", checkpoint_tag)
            # Stop container
            container.stop(timeout=5)
            logger.info("Spun down container: %s", container_name)
            return {"success": True, "status": "checkpointed", "checkpoint_tag": checkpoint_tag}
        except Exception as e:
            logger.error("Error checkpointing container %s: %s", container_name, e)
            return {"success": False, "error": str(e)}

    def delete_on_merge(self, project_key: str, branch_name: str) -> Dict[str, Any]:
        """
        Deletes container and removes checkpoint images once the branch is merged into main.
        """
        container_name = self.get_container_name(project_key, branch_name)
        checkpoint_tag = self.get_checkpoint_tag(project_key, branch_name)

        if not self.client:
            logger.info("[MOCK] Deleted container %s and checkpoint image %s on merge.", container_name, checkpoint_tag)
            sandbox_dir = ROOT_DIR / "sandboxes" / container_name
            if sandbox_dir.exists():
                import shutil
                shutil.rmtree(sandbox_dir, ignore_errors=True)
            return {"success": True, "deleted": True}

        try:
            # 1. Remove container
            try:
                c = self.client.containers.get(container_name)
                c.remove(force=True)
                logger.info("Removed container %s", container_name)
            except NotFound:
                pass

            # 2. Remove checkpoint image
            try:
                self.client.images.remove(image=checkpoint_tag, force=True)
                logger.info("Removed checkpoint image %s", checkpoint_tag)
            except NotFound:
                pass

            return {"success": True, "deleted": True}
        except Exception as e:
            logger.error("Error deleting container/image for %s: %s", container_name, e)
            return {"success": False, "error": str(e)}

    def _simulate_ensure_container(self, container_name, checkpoint_tag, sandbox_dir, branch_name, staged_files, is_new_project):
        """Simulated sandbox for development when Docker daemon is not active."""
        import shutil
        if is_new_project:
            (sandbox_dir / ".git").mkdir(exist_ok=True)
            (sandbox_dir / ".venv").mkdir(exist_ok=True)
        else:
            (sandbox_dir / ".git").mkdir(exist_ok=True)
            (sandbox_dir / ".venv").mkdir(exist_ok=True)

        if staged_files:
            staged_in_sandbox = sandbox_dir / "staged_files"
            staged_in_sandbox.mkdir(exist_ok=True)
            for item in staged_files:
                src = Path(item["staged_path"])
                if src.exists():
                    shutil.copy2(src, staged_in_sandbox / src.name)

        logger.info("Sandbox container %s ready at %s", container_name, sandbox_dir)
        return {
            "success": True,
            "container_id": f"sim_{container_name}",
            "container_name": container_name,
            "status": "ready",
            "checkpoint_tag": checkpoint_tag,
            "workspace_path": str(sandbox_dir)
        }

docker_manager = DockerContainerManager()
