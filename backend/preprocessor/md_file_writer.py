import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from backend.config import get_prompt_output_dir

logger = logging.getLogger("hephaestus.md_file_writer")

class MDFileWriter:
    """
    Handles saving prompt instructions and preparations to markdown (.md) files.
    - Writes prompt.md containing the user prompt instructions.
    - If preparations exist, appends a clearly demarcated <|preparations|> tag section to prompt.md
      and creates preparations.md in the task staging directory.
    - Resolves save directory via get_prompt_output_dir() (supports .env override).
    """

    def __init__(self, base_output_dir: Optional[Path] = None):
        self._custom_base_dir = base_output_dir

    @property
    def base_dir(self) -> Path:
        if self._custom_base_dir:
            self._custom_base_dir.mkdir(parents=True, exist_ok=True)
            return self._custom_base_dir
        return get_prompt_output_dir()

    def get_task_dir(self, task_id: str) -> Path:
        task_dir = self.base_dir / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def write_prompt_and_preparations(
        self,
        task_id: str,
        prompt_text: str,
        preparations: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Writes prompt and optional preparations to markdown file(s).
        - prompt.md contains ONLY the prompt instructions.
        - preparations.md contains ONLY the raw preparation instructions for container/MCP setup.
        
        Returns metadata including resolved file paths and status.
        """
        task_dir = self.get_task_dir(task_id)
        prompt_file = task_dir / "prompt.md"

        # Build prompt.md content containing exclusively the prompt
        clean_prompt = prompt_text.strip()

        has_prep = bool(preparations and preparations.strip())
        prep_file = None

        if has_prep:
            prep_clean = preparations.strip()
            # Write separate preparations.md for Docker/MCP orchestration
            prep_file = task_dir / "preparations.md"
            with open(prep_file, "w", encoding="utf-8") as f:
                f.write(prep_clean)

        # Write prompt.md containing only the prompt
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(clean_prompt)

        logger.info(
            "Wrote prompt markdown to '%s' (preparations=%s)",
            prompt_file,
            has_prep
        )

        return {
            "task_id": task_id,
            "task_staging_dir": str(task_dir),
            "prompt_file_path": str(prompt_file),
            "preparations_file_path": str(prep_file) if prep_file else None,
            "has_preparations": has_prep,
            "preparations": preparations.strip() if has_prep else None,
            "written_content": clean_prompt
        }

md_file_writer = MDFileWriter()
