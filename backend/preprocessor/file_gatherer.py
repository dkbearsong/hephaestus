import os
import re
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from backend.config import preferences

logger = logging.getLogger("hephaestus.files")

class FileGatherer:
    def __init__(self):
        self.container_workspace = preferences.docker.workspace_dir_inside_container

    def extract_and_stage_files(self, prompt_file_path: str, task_staging_dir: str, repo_root: str = "") -> Dict[str, Any]:
        """
        Parses prompt markdown file for <|files|> ... </|files|>.
        Copies specified files to staging, and updates the prompt markdown to point
        to destination paths inside the Docker container (/workspace/staged_files/...).
        """
        prompt_path = Path(prompt_file_path)
        staging_dir = Path(task_staging_dir)
        files_staging_dir = staging_dir / "files"
        files_staging_dir.mkdir(parents=True, exist_ok=True)

        if not prompt_path.exists():
            return {"success": False, "error": "Prompt file does not exist", "files": []}

        content = prompt_path.read_text(encoding="utf-8")

        # Pattern: <|files|> ... </|files|> or <|files|> ... <|endfiles|>
        pattern = re.compile(r"<\|files\|>(.*?)(?:<\/\|files\|>|<\|endfiles\|>|$)", re.DOTALL | re.IGNORECASE)
        match = pattern.search(content)

        staged_manifest = []

        if not match:
            # Check for inline <|files|> filename ...
            inline_pattern = re.compile(r"<\|files\|>\s*([^\n\r]+)", re.IGNORECASE)
            inline_match = inline_pattern.search(content)
            if not inline_match:
                # No files specified
                return {
                    "success": True,
                    "has_files": False,
                    "staged_files": [],
                    "updated_prompt": content
                }
            files_block = inline_match.group(1)
            raw_matched_chunk = inline_match.group(0)
        else:
            files_block = match.group(1)
            raw_matched_chunk = match.group(0)

        # Extract file paths from block (lines or comma-separated)
        raw_paths = []
        for line in files_block.splitlines():
            line = line.strip().strip(",;-*`\"'")
            if line:
                for p in line.split(","):
                    p_clean = p.strip().strip("`\"'")
                    if p_clean and not p_clean.startswith("#"):
                        raw_paths.append(p_clean)

        logger.info("Found %d file paths referenced in prompt: %s", len(raw_paths), raw_paths)

        container_files_block_lines = ["<|files|>"]

        for file_str in raw_paths:
            resolved_source = self._resolve_source_path(file_str, repo_root)
            filename = Path(file_str).name
            container_dest = f"{self.container_workspace}/staged_files/{filename}"
            
            staged_path = files_staging_dir / filename

            if resolved_source and resolved_source.exists() and resolved_source.is_file():
                shutil.copy2(resolved_source, staged_path)
                logger.info("Copied file '%s' -> '%s'", resolved_source, staged_path)
                status = "staged"
            else:
                # Create a placeholder in staging if referenced file doesn't exist yet
                staged_path.touch(exist_ok=True)
                logger.warning("Referenced file '%s' not found locally. Created staging placeholder.", file_str)
                status = "placeholder"

            staged_manifest.append({
                "original_path": file_str,
                "staged_path": str(staged_path),
                "container_dest": container_dest,
                "status": status
            })
            container_files_block_lines.append(f"  - {container_dest}")

        container_files_block_lines.append("</|files|>")
        new_files_block = "\n".join(container_files_block_lines)

        # Replace in content
        updated_content = content.replace(raw_matched_chunk, new_files_block)
        prompt_path.write_text(updated_content, encoding="utf-8")

        return {
            "success": True,
            "has_files": len(staged_manifest) > 0,
            "staged_files": staged_manifest,
            "updated_prompt": updated_content
        }

    def _resolve_source_path(self, path_str: str, repo_root: str = "") -> Optional[Path]:
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return p
        if repo_root:
            repo_p = Path(repo_root) / path_str
            if repo_p.exists():
                return repo_p
        # Current workspace check
        curr_p = Path.cwd() / path_str
        if curr_p.exists():
            return curr_p
        return None

file_gatherer = FileGatherer()
