import re
from pathlib import Path
from typing import Tuple, Dict, Any
from backend.config import STAGING_DIR, preferences

class PromptExtractor:
    def __init__(self):
        self.update_prefix = preferences.jira.update_trigger_prefix # "<|prompt|>"
        self.new_proj_prefix = preferences.jira.new_project_trigger_prefix # "<|prompt-new|>"

    def extract_prompt(self, comment_text: str, task_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Monitors incoming comment or text.
        If it starts with <|prompt|> or <|prompt-new|>:
          - Strips the prefix
          - Detects workflow type ('update' vs 'new_project')
          - Saves clean prompt to staging/{task_id}/prompt.md
          - Returns (True, metadata)
        """
        trimmed = comment_text.strip()
        is_new_project = False
        raw_prompt = ""

        if trimmed.startswith(self.new_proj_prefix):
            is_new_project = True
            raw_prompt = trimmed[len(self.new_proj_prefix):].strip()
        elif trimmed.startswith(self.update_prefix):
            is_new_project = False
            raw_prompt = trimmed[len(self.update_prefix):].strip()
        else:
            # Not an AI prompt trigger
            return False, {}

        # Prepare task staging directory
        task_dir = STAGING_DIR / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = task_dir / "prompt.md"

        # Save to markdown file
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(raw_prompt)

        return True, {
            "task_id": task_id,
            "is_new_project": is_new_project,
            "raw_text": comment_text,
            "cleaned_prompt": raw_prompt,
            "prompt_file_path": str(prompt_file),
            "task_staging_dir": str(task_dir)
        }

prompt_extractor = PromptExtractor()
