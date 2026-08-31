import re
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List
from backend.config import STAGING_DIR, preferences

class PromptExtractor:
    def __init__(self):
        self.update_prefix = preferences.jira.update_trigger_prefix # "<|prompt|>"
        self.new_proj_prefix = preferences.jira.new_project_trigger_prefix # "<|prompt-new|>"
        self.prep_prefix = getattr(preferences.jira, "preparations_trigger_prefix", "<|preparations|>")

    def extract_preparations(self, text: str) -> Tuple[Optional[str], str]:
        """
        Extracts optional <|preparations|> tag content from text.
        Supports both block format (<|preparations|>...</|preparations|>)
        and open format (<|preparations|>... up to next prompt tag or end of text).
        Returns (preparations_content, text_without_preparations).
        """
        if not text or self.prep_prefix not in text:
            return None, text

        # 1. Block tag with explicit closing tag: <|preparations|>...</|preparations|>
        block_pattern = re.compile(
            r"<\|preparations\|>(.*?)(?:<\/\|preparations\|>|<\|endpreparations\|>)",
            re.DOTALL | re.IGNORECASE
        )
        match = block_pattern.search(text)
        if match:
            prep_content = match.group(1).strip()
            remaining = text[:match.start()] + text[match.end():]
            return prep_content, remaining.strip()

        # 2. Open tag ending at <|prompt-new|> or <|prompt|> or <|files|> or end of text
        open_pattern = re.compile(
            r"<\|preparations\|>(.*?)(?=<\|prompt-new\|>|<\|prompt\|>|<\|files\|>|$)",
            re.DOTALL | re.IGNORECASE
        )
        match = open_pattern.search(text)
        if match:
            prep_content = match.group(1).strip()
            remaining = text[:match.start()] + text[match.end():]
            return prep_content, remaining.strip()

        return None, text

    def extract_files(self, text: str) -> Tuple[List[str], str]:
        """
        Extracts list of file paths referenced in <|files|> tag.
        Supports multiline blocks with quotes/spaces, comma-separated paths,
        and inline paths.
        Returns (files_list, text_with_files_block_removed).
        """
        if not text or "<|files|>" not in text:
            return [], text

        block_pattern = re.compile(
            r"<\|files\|>(.*?)(?:<\/\|files\|>|<\|endfiles\|>)",
            re.DOTALL | re.IGNORECASE
        )
        match = block_pattern.search(text)
        if match:
            files_block = match.group(1)
            remaining = text[:match.start()] + text[match.end():]
        else:
            open_pattern = re.compile(
                r"<\|files\|>(.*?)(?=<\|preparations\|>|<\/\|preparations\|>|<\|prompt-new\|>|<\|prompt\|>|$)",
                re.DOTALL | re.IGNORECASE
            )
            match = open_pattern.search(text)
            if match:
                files_block = match.group(1)
                remaining = text[:match.start()] + text[match.end():]
            else:
                return [], text

        raw_paths = []
        for line in files_block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("<|") or line.startswith("</|"):
                continue
            if (line.startswith("'") and line.endswith("'")) or (line.startswith('"') and line.endswith('"')):
                clean_p = line[1:-1].strip()
                if clean_p:
                    raw_paths.append(clean_p)
            else:
                for part in line.split(","):
                    part_clean = part.strip().strip("`\"'")
                    if part_clean and not part_clean.startswith("#") and not part_clean.startswith("<|") and not part_clean.startswith("</|"):
                        raw_paths.append(part_clean)

        return raw_paths, remaining.strip()

    def extract_prompt(self, comment_text: str, task_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Monitors incoming comment or text.
        Extracts:
          - Optional <|preparations|> tag (saved to staging/{task_id}/preparations.md)
          - Prompt trigger tag (<|prompt|> or <|prompt-new|>)
          - Files referenced in <|files|>
          - Saves clean prompt to staging/{task_id}/prompt.md
          - Returns (is_prompt, metadata)
        """
        # Step 1: Extract optional preparations instructions
        preparations, text_without_prep = self.extract_preparations(comment_text)

        trimmed = text_without_prep.strip()
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

        # Extract file paths and isolate pure prompt instructions
        files, prompt_instructions = self.extract_files(raw_prompt)

        # Write prompt and preparations to markdown file(s) via MDFileWriter (prompt terminates at <|files|>)
        from backend.preprocessor.md_file_writer import md_file_writer
        writer_res = md_file_writer.write_prompt_and_preparations(
            task_id=task_id,
            prompt_text=prompt_instructions,
            preparations=preparations
        )

        return True, {
            "task_id": task_id,
            "is_new_project": is_new_project,
            "raw_text": comment_text,
            "cleaned_prompt": raw_prompt,
            "prompt_instructions": prompt_instructions,
            "files": files,
            "has_files": len(files) > 0,
            "preparations": preparations,
            "has_preparations": preparations is not None,
            "prompt_file_path": writer_res["prompt_file_path"],
            "preparations_file_path": writer_res["preparations_file_path"],
            "task_staging_dir": writer_res["task_staging_dir"],
            "written_content": writer_res["written_content"]
        }

prompt_extractor = PromptExtractor()

