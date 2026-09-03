"""
Preparation Agent Integration
"""

import os
import json
import shutil
from typing import Dict, Any, List
from backend.workspace_orchestrator.scaffolding import copy_recursive
from backend.workspace_orchestrator.types import PrepSummary, DetectedCommands

def run_prep_agent(
    working_directory: str,
    branch_name: str,
    staging_dir: str,
    composed_instructions: str
) -> PrepSummary:
    files_modified: List[str] = []

    prompt_md = ""
    prompt_path = os.path.join(staging_dir, "prompt.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_md = f.read()

    # Move staged/inbox files to intended module paths
    inbox_dir = os.path.join(working_directory, ".harness_inbox")
    if os.path.exists(inbox_dir):
        for item in os.listdir(inbox_dir):
            src_path = os.path.join(inbox_dir, item)
            target_subdir = ""

            if item.endswith((".ts", ".js", ".jsx", ".tsx")):
                target_subdir = "src"
            elif item.endswith(".py"):
                target_subdir = "app"
            else:
                target_subdir = "config"

            dest_dir = os.path.join(working_directory, target_subdir)
            os.makedirs(dest_dir, exist_ok=True)

            dest_path = os.path.join(dest_dir, item)
            copy_recursive(src_path, dest_path)
            rel_dest = os.path.relpath(dest_path, working_directory)
            files_modified.append(rel_dest)

            try:
                if os.path.isdir(src_path):
                    shutil.rmtree(src_path)
                else:
                    os.remove(src_path)
            except Exception:
                pass

        try:
            if not os.listdir(inbox_dir):
                os.rmdir(inbox_dir)
        except Exception:
            pass

    detected_commands: DetectedCommands = {}

    pkg_json_path = os.path.join(working_directory, "package.json")
    if os.path.exists(pkg_json_path):
        detected_commands["build"] = "npm run build"
        detected_commands["test"] = "npm test"
        detected_commands["lint"] = "npm run lint"

        if (
            "dependency" in composed_instructions.lower()
            or "install" in composed_instructions.lower()
            or "dependency" in prompt_md.lower()
        ):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg_data = json.load(f)
                pkg_data["scripts"] = pkg_data.get("scripts", {})
                if "build" not in pkg_data["scripts"]:
                    pkg_data["scripts"]["build"] = "tsc"
                if "test" not in pkg_data["scripts"]:
                    pkg_data["scripts"]["test"] = "node --test"

                with open(pkg_json_path, "w", encoding="utf-8") as f:
                    json.dump(pkg_data, f, indent=2)

                if "package.json" not in files_modified:
                    files_modified.append("package.json")
            except Exception:
                pass
    else:
        if os.path.exists(os.path.join(working_directory, "requirements.txt")) or os.path.exists(os.path.join(working_directory, "pytest.ini")):
            detected_commands["test"] = "pytest"
            detected_commands["lint"] = "flake8"

    if "STATUS: BLOCKED" in composed_instructions or "STATUS: BLOCKED" in prompt_md:
        return {
            "status": "BLOCKED",
            "workingDirectory": working_directory,
            "branchName": branch_name,
            "detectedCommands": detected_commands,
            "filesModified": files_modified,
            "blockerReason": "Blocked by preparations directive or missing required dependency setup",
        }

    return {
        "status": "READY",
        "workingDirectory": working_directory,
        "branchName": branch_name,
        "detectedCommands": detected_commands,
        "filesModified": files_modified,
    }
