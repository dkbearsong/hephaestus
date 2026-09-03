"""
Dynamic Provider Preparation Engine
"""

import os
import json
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any
from backend.workspace_orchestrator.types import ProviderPrepResult

def prepare_provider(target_platform: str, working_directory: str, staging_dir: str) -> ProviderPrepResult:
    platform_configs: Dict[str, str] = {}
    platform_rules = []

    if target_platform == "GOOGLE_JULES":
        platform_rules.append("PROVIDER RULE (GOOGLE_JULES): Zero uncommitted files requirement enforced.")
        platform_rules.append("PROVIDER RULE (GOOGLE_JULES): Ensure .jules/ configuration is present and updated.")
        platform_rules.append("PROVIDER RULE (GOOGLE_JULES): Set build and test hooks into standard repo configs.")

        jules_dir = os.path.join(working_directory, ".jules")
        os.makedirs(jules_dir, exist_ok=True)
        jules_config_path = os.path.join(jules_dir, "config.json")

        existing_config = {}
        if os.path.exists(jules_config_path):
            try:
                with open(jules_config_path, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            except Exception:
                existing_config = {}

        updated_config = {
            **existing_config,
            "provider": "GOOGLE_JULES",
            "hooks": {
                "build": "npm run build",
                "test": "npm test",
            },
            "enforceZeroUncommitted": True,
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        }

        config_str = json.dumps(updated_config, indent=2)
        with open(jules_config_path, "w", encoding="utf-8") as f:
            f.write(config_str)
        platform_configs[".jules/config.json"] = config_str

        try:
            subprocess.run(["git", "add", ".jules/"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "commit", "-m", "Configure GOOGLE_JULES platform settings"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            pass

    elif target_platform == "CODEX_CLOUD":
        platform_rules.append("PROVIDER RULE (CODEX_CLOUD): Verify top-level execution entry points.")
        platform_rules.append("PROVIDER RULE (CODEX_CLOUD): Format task metadata for GitHub App webhook trigger.")

        codex_dir = os.path.join(working_directory, ".codex")
        os.makedirs(codex_dir, exist_ok=True)
        metadata_path = os.path.join(codex_dir, "task_metadata.json")

        metadata = {
            "provider": "CODEX_CLOUD",
            "webhookTriggered": True,
            "entryPoints": ["src/index.js", "src/index.ts", "index.js", "main.py", "package.json"],
            "configuredAt": datetime.now(timezone.utc).isoformat(),
        }

        metadata_str = json.dumps(metadata, indent=2)
        with open(metadata_path, "w", encoding="utf-8") as f:
            f.write(metadata_str)
        platform_configs[".codex/task_metadata.json"] = metadata_str

    elif target_platform == "LOCAL_CONTAINER":
        platform_rules.append("PROVIDER RULE (LOCAL_CONTAINER): Configure Docker mount points.")
        platform_rules.append("PROVIDER RULE (LOCAL_CONTAINER): Export .env variables from staged configs.")
        platform_rules.append("PROVIDER RULE (LOCAL_CONTAINER): Ensure execute permissions on scripts.")

        docker_mounts = {
            "workspace": working_directory,
            "mountPoints": [
                {"host": working_directory, "container": "/workspace", "mode": "rw"}
            ],
        }
        mounts_str = json.dumps(docker_mounts, indent=2)
        with open(os.path.join(working_directory, ".docker_mounts.json"), "w", encoding="utf-8") as f:
            f.write(mounts_str)
        platform_configs[".docker_mounts.json"] = mounts_str

        staged_env_path = os.path.join(staging_dir, "staged_files", ".env")
        env_content = "ENVIRONMENT=LOCAL_CONTAINER\n"
        if os.path.exists(staged_env_path):
            with open(staged_env_path, "r", encoding="utf-8") as f:
                env_content += f.read() + "\n"
        with open(os.path.join(working_directory, ".env"), "w", encoding="utf-8") as f:
            f.write(env_content)
        platform_configs[".env"] = env_content

        if os.path.exists(working_directory):
            for entry in os.listdir(working_directory):
                if entry.endswith(".sh"):
                    script_path = os.path.join(working_directory, entry)
                    try:
                        os.chmod(script_path, 0o755)
                    except Exception:
                        pass

    preparations_md = ""
    prep_path = os.path.join(staging_dir, "preparations.md")
    if os.path.exists(prep_path):
        with open(prep_path, "r", encoding="utf-8") as f:
            preparations_md = f.read()

    composed_instructions = "\n".join([
        "=== TARGET PLATFORM CONSTRAINTS ===",
        *platform_rules,
        "",
        "=== USER PREPARATIONS INSTRUCTIONS ===",
        preparations_md or "(No specific preparations.md provided)",
    ])

    return {
        "composedInstructions": composed_instructions,
        "platformConfigs": platform_configs,
    }
