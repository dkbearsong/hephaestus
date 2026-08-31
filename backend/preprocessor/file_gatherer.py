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

    def extract_and_stage_files(
        self,
        prompt_file_path: str,
        task_staging_dir: str,
        repo_root: str = "",
        preparations: Optional[str] = None,
        files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Stages specified files into the task staging directory (staging/{task_id}/files/).
        The prompt.md file terminates when it sees <|files|>, and preparations instructions
        are preserved cleanly under <|preparations|>.
        Rewrites file references in the prompt to match container destinations.
        """
        prompt_path = Path(prompt_file_path)
        staging_dir = Path(task_staging_dir)
        files_staging_dir = staging_dir / "files"
        files_staging_dir.mkdir(parents=True, exist_ok=True)

        prep_file = staging_dir / "preparations.md"
        resolved_prep = preparations
        if not resolved_prep and prep_file.exists():
            resolved_prep = prep_file.read_text(encoding="utf-8")
        elif resolved_prep and not prep_file.exists():
            prep_file.write_text(resolved_prep, encoding="utf-8")

        if not prompt_path.exists():
            return {
                "success": False,
                "error": "Prompt file does not exist",
                "files": [],
                "preparations": resolved_prep,
                "has_preparations": bool(resolved_prep),
                "preparations_file_path": str(prep_file) if prep_file.exists() else None
            }

        content = prompt_path.read_text(encoding="utf-8")

        # Determine raw paths to stage
        raw_paths = []
        if files is not None:
            raw_paths = [f for f in files if f and not f.startswith("<|") and not f.startswith("</|")]

        # Check if prompt.md contains <|files|> tag block that needs to be stripped
        block_pattern = re.compile(r"<\|files\|>(.*?)(?:<\/\|files\|>|<\|endfiles\|>)", re.DOTALL | re.IGNORECASE)
        match = block_pattern.search(content)

        if match:
            if not raw_paths:
                files_block = match.group(1)
                for line in files_block.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("<|") or line.startswith("</|"):
                        continue
                    if (line.startswith("'") and line.endswith("'")) or (line.startswith('"') and line.endswith('"')):
                        clean_p = line[1:-1].strip()
                        if clean_p:
                            raw_paths.append(clean_p)
                    else:
                        for p in line.split(","):
                            p_clean = p.strip().strip("`\"'")
                            if p_clean and not p_clean.startswith("#") and not p_clean.startswith("<|") and not p_clean.startswith("</|"):
                                raw_paths.append(p_clean)
            match_start = match.start()
            match_end = match.end()
            # Strip <|files|> block from prompt.md so prompt terminates when it sees <|files|>
            tail = content[match_end:].lstrip("\r\n")
            if tail:
                updated_content = content[:match_start].rstrip() + "\n\n" + tail
            else:
                updated_content = content[:match_start].rstrip() + "\n"
        else:
            open_pattern = re.compile(
                r"<\|files\|>(.*?)(?=<\|preparations\|>|<\/\|preparations\|>|<\|prompt-new\|>|<\|prompt\|>|$)",
                re.DOTALL | re.IGNORECASE
            )
            open_match = open_pattern.search(content)
            if open_match and open_match.group(1).strip():
                if not raw_paths:
                    files_block = open_match.group(1)
                    for line in files_block.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("<|") or line.startswith("</|"):
                            continue
                        if (line.startswith("'") and line.endswith("'")) or (line.startswith('"') and line.endswith('"')):
                            clean_p = line[1:-1].strip()
                            if clean_p:
                                raw_paths.append(clean_p)
                        else:
                            for p in line.split(","):
                                p_clean = p.strip().strip("`\"'")
                                if p_clean and not p_clean.startswith("#") and not p_clean.startswith("<|") and not p_clean.startswith("</|"):
                                    raw_paths.append(p_clean)
                match_start = open_match.start()
                match_end = open_match.end()
                tail = content[match_end:].lstrip("\r\n")
                if tail:
                    updated_content = content[:match_start].rstrip() + "\n\n" + tail
                else:
                    updated_content = content[:match_start].rstrip() + "\n"
            else:
                updated_content = content

        staged_manifest = []
        logger.info("Found %d file paths referenced for staging: %s", len(raw_paths), raw_paths)

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

            if file_str in updated_content:
                updated_content = updated_content.replace(file_str, container_dest)
            elif filename in updated_content and container_dest not in updated_content:
                updated_content = updated_content.replace(filename, container_dest)

            staged_manifest.append({
                "original_path": file_str,
                "staged_path": str(staged_path),
                "container_dest": container_dest,
                "status": status
            })

        # Save rewritten content to prompt.md
        prompt_path.write_text(updated_content, encoding="utf-8")

        return {
            "success": True,
            "has_files": len(staged_manifest) > 0,
            "staged_files": staged_manifest,
            "updated_prompt": updated_content,
            "preparations": resolved_prep,
            "has_preparations": bool(resolved_prep),
            "preparations_file_path": str(prep_file) if prep_file.exists() else None
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
