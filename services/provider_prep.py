import json
import os
import stat
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from services.models import ProviderConfig
from services.scaffolding import GitRunner
from profiles.registry import inject_profile_configurations, get_execution_profile

logger = logging.getLogger("hephaestus.services.provider_prep")


class ProviderPrepEngine:
    """
    Dynamic Provider Preparation Engine.
    Injects platform-specific configurations, enforces environment rules,
    and merges constraints with user preparations.md instructions.
    """

    def prepare(
        self,
        working_dir: Path,
        target_platform: str,
        staging_dir: Path,
        ticket_key: str
    ) -> ProviderConfig:
        """
        Executes provider-specific setup on the workspace.
        """
        logger.info(f"Executing provider preparation for {target_platform} in {working_dir}")

        plat_key = str(target_platform).strip().upper().replace("-", "_")
        if plat_key in ("GOOGLE_JULES", "JULES"):
            return self._prep_google_jules(working_dir, staging_dir, ticket_key)
        elif plat_key in ("CODEX_CLOUD", "CODEX", "OPENAI_CODEX_CLOUD"):
            return self._prep_codex_cloud(working_dir, staging_dir, ticket_key)
        elif plat_key in ("LOCAL_CONTAINER", "LOCAL", "DOCKER_SANDBOX", "ANTIGRAVITY"):
            return self._prep_local_container(working_dir, staging_dir, ticket_key)
        elif plat_key in ("GROK_BUILD", "GROK"):
            return self._prep_grok_build(working_dir, staging_dir, ticket_key)
        elif plat_key in ("DEVIN_AI", "DEVIN", "COGNITION"):
            return self._prep_devin_ai(working_dir, staging_dir, ticket_key)
        elif plat_key in ("CURSOR_DEVCONTAINER", "CURSOR", "CURSOR_DEV_CONTAINER"):
            return self._prep_cursor_devcontainer(working_dir, staging_dir, ticket_key)
        else:
            raise ValueError(f"Unknown target platform: {target_platform}")

    def _prep_google_jules(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        GOOGLE_JULES:
        1. Generates/updates .jules/ configuration.
        2. Sets build/test hooks into standard repo configs.
        3. Enforces zero uncommitted files (commits any pending changes).
        """
        rules = [
            "Enforce zero uncommitted files",
            "Generate/update .jules/ configuration",
            "Set build/test hooks into standard repo configs"
        ]
        manifest_files = []
        hooks = {}

        # 1. Detect test/build commands
        test_hook = "pytest"
        build_hook = None
        if (working_dir / "package.json").exists():
            test_hook = "npm test"
            build_hook = "npm run build"
        elif (working_dir / "Cargo.toml").exists():
            test_hook = "cargo test"
            build_hook = "cargo build"
        elif (working_dir / "go.mod").exists():
            test_hook = "go test ./..."
            build_hook = "go build"

        hooks["test"] = test_hook
        if build_hook:
            hooks["build"] = build_hook

        # 2. Generate/update .jules/config.yaml
        jules_dir = working_dir / ".jules"
        jules_dir.mkdir(parents=True, exist_ok=True)
        jules_cfg = jules_dir / "config.yaml"

        config_data = {
            "version": 1,
            "ticket_key": ticket_key,
            "platform": "google_jules",
            "execution": {
                "enforce_zero_uncommitted_files": True,
                "auto_execute_tests": True
            },
            "hooks": hooks
        }

        # Write clean YAML representation
        yaml_lines = [
            "version: 1",
            f"ticket_key: {ticket_key}",
            "platform: google_jules",
            "execution:",
            "  enforce_zero_uncommitted_files: true",
            "  auto_execute_tests: true",
            "hooks:",
            f"  test: {test_hook}"
        ]
        if build_hook:
            yaml_lines.append(f"  build: {build_hook}")
        else:
            yaml_lines.append("  build: null")

        jules_cfg.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        manifest_files.append(".jules/config.yaml")

        # 3. If pytest is used, ensure pytest.ini exists or test config is present
        if test_hook == "pytest":
            pytest_ini = working_dir / "pytest.ini"
            if not pytest_ini.exists() and not (working_dir / "pyproject.toml").exists():
                pytest_ini.write_text(
                    "[pytest]\ntestpaths = tests test\npython_files = test_*.py *_test.py\n",
                    encoding="utf-8"
                )
                manifest_files.append("pytest.ini")

        # 4. Enforce zero uncommitted files:
        # Check git status and commit everything so Google Jules starts with a clean tree
        try:
            status_res = GitRunner.run_git(["status", "--porcelain"], cwd=working_dir)
            if status_res.stdout.strip():
                GitRunner.run_git(["add", "."], cwd=working_dir)
                GitRunner.run_git(
                    ["commit", "-m", f"chore(jules): align workspace configuration for {ticket_key}"],
                    cwd=working_dir
                )
                logger.info("Committed pending workspace configuration for Google Jules zero-uncommitted rule")
        except Exception as e:
            logger.warning(f"Git status / auto-commit check encountered: {e}")

        return ProviderConfig(
            platform="GOOGLE_JULES",
            rules_applied=rules,
            manifest_files=manifest_files,
            environment_variables={},
            mount_points={},
            entry_points_verified=[],
            hooks_configured=hooks
        )

    def _prep_codex_cloud(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        CODEX_CLOUD:
        1. Verifies top-level execution entry points.
        2. Formats task metadata for GitHub App webhook trigger.
        """
        rules = [
            "Verify top-level execution entry points",
            "Format task metadata for GitHub App webhook trigger"
        ]
        manifest_files = []

        # 1. Verify entry points
        common_entrypoints = [
            "main.py", "app.py", "run.py", "index.js", "index.ts",
            "src/main.py", "src/index.js", "src/index.ts",
            "pyproject.toml", "package.json", "setup.py"
        ]
        verified_entrypoints = [ep for ep in common_entrypoints if (working_dir / ep).exists()]

        # If no entry point exists, create a default main.py entry point
        if not verified_entrypoints:
            default_entry = working_dir / "main.py"
            default_entry.write_text(
                'if __name__ == "__main__":\n    print("Entry point initialized for Codex Cloud")\n',
                encoding="utf-8"
            )
            verified_entrypoints.append("main.py")
            manifest_files.append("main.py")

        # 2. Format task metadata for GitHub App webhook trigger
        codex_dir = working_dir / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        meta_file = codex_dir / "task_metadata.json"

        metadata = {
            "ticket_key": ticket_key,
            "trigger_event": "github_app_webhook",
            "target_platform": "CODEX_CLOUD",
            "entrypoints": verified_entrypoints,
            "status": "CONFIGURED",
            "sandbox_requirements": {
                "timeout_seconds": 600,
                "allow_network": True
            }
        }
        meta_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        manifest_files.append(".codex/task_metadata.json")

        return ProviderConfig(
            platform="CODEX_CLOUD",
            rules_applied=rules,
            manifest_files=manifest_files,
            environment_variables={},
            mount_points={},
            entry_points_verified=verified_entrypoints,
            hooks_configured={}
        )

    def _prep_local_container(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        LOCAL_CONTAINER:
        1. Configures Docker mount points.
        2. Exports .env variables from staged configs.
        3. Ensures execution permissions on execution scripts.
        """
        rules = [
            "Configure Docker mount points",
            "Export .env variables from staged configs",
            "Ensure permissions on execution scripts"
        ]
        manifest_files = []

        # 1. Configures Docker mount points
        docker_dir = working_dir / ".docker"
        docker_dir.mkdir(parents=True, exist_ok=True)
        mounts_path = docker_dir / "mounts.json"

        mount_spec = {
            "workspace_source": str(working_dir.resolve()),
            "workspace_target": "/workspace",
            "mode": "rw",
            "ticket_key": ticket_key
        }
        mounts_path.write_text(json.dumps(mount_spec, indent=2), encoding="utf-8")
        manifest_files.append(".docker/mounts.json")

        # 2. Export .env variables from staged configs
        exported_envs: Dict[str, str] = {}
        # Search staging_dir and .harness_inbox for .env files
        candidate_env_dirs = [
            staging_dir,
            staging_dir / "staged_files",
            staging_dir / "files",
            working_dir / ".harness_inbox"
        ]
        env_files = []
        for d in candidate_env_dirs:
            if d.exists():
                for item in d.glob("*.env*"):
                    env_files.append(item)

        for ef in env_files:
            try:
                for line in ef.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        exported_envs[k.strip()] = v.strip().strip("'\"")
            except Exception as ex:
                logger.warning(f"Could not parse env file {ef}: {ex}")

        # Write or update workspace .env
        workspace_env = working_dir / ".env"
        current_env_lines = []
        if workspace_env.exists():
            current_env_lines = workspace_env.read_text(encoding="utf-8").splitlines()

        current_keys = set()
        for l in current_env_lines:
            l = l.strip()
            if l and not l.startswith("#") and "=" in l:
                current_keys.add(l.split("=", 1)[0].strip())

        new_lines = list(current_env_lines)
        for k, v in exported_envs.items():
            if k not in current_keys:
                new_lines.append(f"{k}={v}")

        if not workspace_env.exists() and not new_lines:
            new_lines = [
                f"# Local Container runtime environment for {ticket_key}",
                "PYTHONUNBUFFERED=1",
                "ENVIRONMENT=local_container"
            ]

        workspace_env.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        manifest_files.append(".env")

        # 3. Ensure permissions on execution scripts
        # Recursively find *.sh or scripts in bin/ / scripts/ and apply chmod +x
        for p in working_dir.rglob("*.sh"):
            if ".git" in p.parts:
                continue
            try:
                current_mode = os.stat(p).st_mode
                os.chmod(p, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                logger.info(f"Granted execution permission to script: {p.relative_to(working_dir)}")
            except Exception as e:
                logger.warning(f"Failed to chmod {p}: {e}")

        for script_dir in [working_dir / "bin", working_dir / "scripts"]:
            if script_dir.exists() and script_dir.is_dir():
                for p in script_dir.iterdir():
                    if p.is_file():
                        try:
                            current_mode = os.stat(p).st_mode
                            os.chmod(p, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                        except Exception as e:
                            logger.warning(f"Failed to chmod {p}: {e}")

        return ProviderConfig(
            platform="LOCAL_CONTAINER",
            rules_applied=rules,
            manifest_files=manifest_files,
            environment_variables=exported_envs,
            mount_points={"/workspace": str(working_dir.resolve())},
            entry_points_verified=[],
            hooks_configured={}
        )

    def _prep_grok_build(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        GROK_BUILD:
        1. Exports structural map repo_tree.txt.
        2. Generates .grok/build-config.json mapping preparation files.
        3. Enforces explicit allowed execution steps.
        """
        rules = [
            "Export structural map repo_tree.txt",
            "Map declared preparation files into build-config.json",
            "Enforce explicit allowed execution steps"
        ]
        # Read preparations.md if available
        prep_md = staging_dir / "preparations.md"
        preparations_content = prep_md.read_text(encoding="utf-8") if prep_md.exists() else ""
        context = {
            "ticket_key": ticket_key,
            "preparations": preparations_content,
            "instructions": f"Execute autonomous build and generation for {ticket_key}"
        }
        injected = inject_profile_configurations("GROK_BUILD", working_dir, context)
        return ProviderConfig(
            platform="GROK_BUILD",
            rules_applied=rules,
            manifest_files=injected,
            environment_variables={},
            mount_points={},
            entry_points_verified=[],
            hooks_configured={"build": "build-config.json"}
        )

    def _prep_devin_ai(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        DEVIN_AI:
        1. Injects multi-step planning directive devin_instructions.md.
        2. Injects reproducible sandbox scripts (devin_setup.sh, devin_test.sh).
        3. Enforces executable permissions (chmod +x) on scripts.
        """
        rules = [
            "Inject multi-step planning framework instructions",
            "Provide reproducible sandbox scripts with executable permissions"
        ]
        context = {
            "ticket_key": ticket_key,
            "instructions": f"Resolve task {ticket_key} through Devin autonomous engineering framework"
        }
        injected = inject_profile_configurations("DEVIN_AI", working_dir, context)
        return ProviderConfig(
            platform="DEVIN_AI",
            rules_applied=rules,
            manifest_files=injected,
            environment_variables={},
            mount_points={},
            entry_points_verified=["scripts/devin_setup.sh", "scripts/devin_test.sh"],
            hooks_configured={"setup": "scripts/devin_setup.sh", "test": "scripts/devin_test.sh"}
        )

    def _prep_cursor_devcontainer(self, working_dir: Path, staging_dir: Path, ticket_key: str) -> ProviderConfig:
        """
        CURSOR_DEVCONTAINER:
        1. Fully configures .devcontainer/devcontainer.json.
        2. Configures customizations.cursor block with rules and tool authorizations.
        3. Configures postCreateCommand for dependency setup.
        """
        rules = [
            "Configure OCI devcontainer specification",
            "Configure customizations.cursor block with rules and tool authorizations",
            "Configure postCreateCommand for dependency setup"
        ]
        context = {
            "ticket_key": ticket_key
        }
        injected = inject_profile_configurations("CURSOR_DEVCONTAINER", working_dir, context)
        return ProviderConfig(
            platform="CURSOR_DEVCONTAINER",
            rules_applied=rules,
            manifest_files=injected,
            environment_variables={},
            mount_points={"/workspace": "${localWorkspaceFolder}"},
            entry_points_verified=[],
            hooks_configured={"postCreateCommand": "configured"}
        )

    def merge_instructions(
        self,
        platform_config: ProviderConfig,
        preparations_content: Optional[str] = None
    ) -> str:
        """
        Merges provider constraints with the user's preparations.md to compose
        the prompt payload for the Preparation Agent.
        """
        sections = [
            "# WORKSPACE PREPARATION INSTRUCTIONS",
            "",
            "## PLATFORM EXECUTION RULES & CONSTRAINTS",
            f"- Target Platform: **{platform_config.platform}**",
            "- Rules Enforced:"
        ]
        for rule in platform_config.rules_applied:
            sections.append(f"  * {rule}")

        if platform_config.manifest_files:
            sections.append(f"- Generated Manifest Files: {', '.join(platform_config.manifest_files)}")

        if platform_config.mount_points:
            sections.append(f"- Docker Volume Mounts: {json.dumps(platform_config.mount_points)}")

        if platform_config.entry_points_verified:
            sections.append(f"- Verified Entry Points: {', '.join(platform_config.entry_points_verified)}")

        if platform_config.hooks_configured:
            sections.append(f"- Configured Hooks: {json.dumps(platform_config.hooks_configured)}")

        sections.append("")
        sections.append("## USER PREPARATIONS INSTRUCTIONS (preparations.md)")
        if preparations_content and preparations_content.strip():
            sections.append(preparations_content.strip())
        else:
            sections.append("*(No custom preparations.md provided; perform baseline workspace organization)*")

        sections.append("")
        sections.append("## AGENT OBJECTIVE")
        sections.append(
            "1. Inspect files currently staged in the workspace or in .harness_inbox/.\n"
            "2. Relocate staged/inbox files to their appropriate repository module paths.\n"
            "3. Update dependency declarations (e.g. requirements.txt, pyproject.toml, package.json) "
            "if indicated by the preparations instructions.\n"
            "4. NEVER write the actual feature code requested in prompt.md.\n"
            "5. Detect build, test, and lint commands and report the final PrepSummary status."
        )

        return "\n".join(sections)


provider_prep_engine = ProviderPrepEngine()
