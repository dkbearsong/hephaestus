from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class HarnessResult(BaseModel):
    status: str # 'completed', 'paused_waiting_input', 'failed'
    summary_changes: str = ""
    what_was_wrong: str = ""
    what_was_done: str = ""
    user_check_items: List[str] = Field(default_factory=list)
    git_diff: str = ""
    full_log: str = ""
    paused_reason: Optional[str] = None
    question_for_user: Optional[str] = None
    requested_permission: Optional[Dict[str, Any]] = None

class BaseCodingHarness(ABC):
    @abstractmethod
    def run_task(
        self,
        prompt: str,
        container_info: Dict[str, Any],
        project_config: Dict[str, Any],
        system_prompt_additions: str = "",
        chat_context: Optional[List[Dict[str, Any]]] = None
    ) -> HarnessResult:
        """Executes the coding prompt within the branch container."""
        pass
