"""
Deterministic Scaffolding Engine
"""

import os
import shutil
import time
import subprocess
from typing import Dict, Any, List
from backend.workspace_orchestrator.types import ScaffoldResult

DEFAULT_GITIGNORE = """# Dependencies
node_modules/
.venv/
venv/
__pycache__/

# Build outputs
dist/
build/
*.so

# Environment & local files
.env
.env.local
.DS_Store
"""

DEFAULT_README = """# Project Workspace

Auto-scaffolded workspace for Jira ticket task.
"""

DEFAULT_LICENSE = """MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to do so.
"""

def copy_recursive(src: str, dest: str) -> None:
    """Recursively copies files or directories from src to dest."""
    if not os.path.exists(src):
        return
    if os.path.isdir(src):
        os.makedirs(dest, exist_ok=True)
        for item in os.listdir(src):
            copy_recursive(os.path.join(src, item), os.path.join(dest, item))
    else:
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dest)

def scaffold_workspace(payload: Dict[str, Any]) -> ScaffoldResult:
    ticket_key = payload.get("ticketKey", "TASK")
    mode = payload.get("mode", "PROMPT_NEW")
    target_platform = payload.get("targetPlatform", "LOCAL_CONTAINER")
    repo_url = payload.get("repoUrl")
    staging_dir = payload.get("stagingDir", "")
    workspaces_root = payload.get("workspacesRoot", ".")
    github_token = payload.get("githubToken")

    timestamp = int(time.time() * 1000)
    working_directory = os.path.abspath(os.path.join(workspaces_root, f"{ticket_key}_{timestamp}"))
    os.makedirs(working_directory, exist_ok=True)

    staged_files_dir = os.path.join(staging_dir, "staged_files")
    staged_files_copied: List[str] = []

    if mode == "PROMPT_NEW":
        try:
            subprocess.run(["git", "init", "-b", "main"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            subprocess.run(["git", "init"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            subprocess.run(["git", "config", "user.name", "Hephaestus Agent"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "agent@hephaestus.local"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            pass

        # Unpack base starter template
        gitignore_path = os.path.join(working_directory, ".gitignore")
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_GITIGNORE)

        readme_path = os.path.join(working_directory, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_README)

        license_path = os.path.join(working_directory, "LICENSE")
        if not os.path.exists(license_path):
            with open(license_path, "w", encoding="utf-8") as f:
                f.write(DEFAULT_LICENSE)

        # Inject baseline configuration
        if target_platform == "GOOGLE_JULES":
            jules_dir = os.path.join(working_directory, ".jules")
            os.makedirs(jules_dir, exist_ok=True)
            with open(os.path.join(jules_dir, "config.json"), "w", encoding="utf-8") as f:
                f.write(f'{{\n  "ticketKey": "{ticket_key}"\n}}\n')
        elif target_platform == "CODEX_CLOUD":
            codex_dir = os.path.join(working_directory, ".codex")
            os.makedirs(codex_dir, exist_ok=True)
            with open(os.path.join(codex_dir, "instructions.md"), "w", encoding="utf-8") as f:
                f.write(f"# Codex Cloud Instructions for {ticket_key}\n")
        elif target_platform == "LOCAL_CONTAINER":
            env_path = os.path.join(working_directory, ".env.example")
            if not os.path.exists(env_path):
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(f"TICKET_KEY={ticket_key}\n")

        # Copy staged files directly into workspace root
        if os.path.exists(staged_files_dir):
            for item in os.listdir(staged_files_dir):
                src_path = os.path.join(staged_files_dir, item)
                dest_path = os.path.join(working_directory, item)
                copy_recursive(src_path, dest_path)
                staged_files_copied.append(item)

        try:
            subprocess.run(["git", "add", "."], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "commit", "-m", "Initial commit from starter template"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            pass

        return {
            "workingDirectory": working_directory,
            "branchName": "main",
            "stagedFilesCopied": staged_files_copied,
        }
    else:
        # PROMPT mode
        clone_url = repo_url or ""
        if github_token and clone_url.startswith("https://github.com/"):
            url_body = clone_url.replace("https://github.com/", "")
            clone_url = f"https://x-access-token:{github_token}@github.com/{url_body}"

        if clone_url:
            subprocess.run(["git", "clone", clone_url, working_directory], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            subprocess.run(["git", "init"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        try:
            subprocess.run(["git", "config", "user.name", "Hephaestus Agent"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "config", "user.email", "agent@hephaestus.local"], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            pass

        branch_name = f"jira-{ticket_key}-agent"
        try:
            subprocess.run(["git", "checkout", "-b", branch_name], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            subprocess.run(["git", "checkout", branch_name], cwd=working_directory, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        inbox_dir = os.path.join(working_directory, ".harness_inbox")
        os.makedirs(inbox_dir, exist_ok=True)

        if os.path.exists(staged_files_dir):
            for item in os.listdir(staged_files_dir):
                src_path = os.path.join(staged_files_dir, item)
                dest_path = os.path.join(inbox_dir, item)
                copy_recursive(src_path, dest_path)
                staged_files_copied.append(f".harness_inbox/{item}")

        return {
            "workingDirectory": working_directory,
            "branchName": branch_name,
            "stagedFilesCopied": staged_files_copied,
        }
