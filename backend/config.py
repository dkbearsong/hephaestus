import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load root .env
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

class AntigravityConfig(BaseModel):
    headless_mode: bool = True
    remote_control: bool = True
    socket_path: str = "/var/run/antigravity.sock"
    default_model: str = "gemini-3.7-flash"
    timeout_seconds: int = 600
    auto_execute_commands: bool = True
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "pypi.org"])

class LangGraphConfig(BaseModel):
    model: str = "gemini-3.7-flash"
    max_iterations: int = 25
    checkpoint_storage: str = "postgres"

class PreparationsSettings(BaseModel):
    enabled: bool = True
    provider: str = "gemini" # 'chatgpt' | 'gemini' | 'claude' | 'grok' | 'openrouter' | 'groq' | 'huggingface' | 'nvidia' | 'lm_studio' | 'ollama'
    model: str = "gemini-2.5-flash"
    max_iterations: int = 10
    temperature: float = 0.2
    available_tools: List[str] = Field(default_factory=lambda: ["datetime_tool", "postgres_inspector", "test_runner"])
    endpoints: Dict[str, str] = Field(default_factory=lambda: {
        "lm_studio": "http://localhost:1234/v1",
        "ollama": "http://localhost:11434/v1",
        "openai": "https://api.openai.com/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
        "claude": "https://api.anthropic.com/v1",
        "grok": "https://api.x.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "groq": "https://api.groq.com/openai/v1",
        "huggingface": "https://api-inference.huggingface.co/v1",
        "nvidia": "https://integrate.api.nvidia.com/v1"
    })

class HarnessSettings(BaseModel):
    active: str = "antigravity_daemon"
    antigravity_daemon: AntigravityConfig = Field(default_factory=AntigravityConfig)
    langgraph_agent: LangGraphConfig = Field(default_factory=LangGraphConfig)

class JiraSettings(BaseModel):
    trigger_label: str = "ai-code"
    new_project_trigger_prefix: str = "<|prompt-new|>"
    update_trigger_prefix: str = "<|prompt|>"
    preparations_trigger_prefix: str = "<|preparations|>"
    completion_label: str = "ai-merged"
    auto_remove_trigger_label: bool = True
    transition_on_merge: str = "Done"

class DockerSettings(BaseModel):
    default_base_image: str = "python:3.12-slim"
    container_prefix: str = "hephaestus_"
    checkpoint_image_prefix: str = "hephaestus-checkpoint:"
    workspace_dir_inside_container: str = "/workspace"
    auto_commit_on_pause: bool = True
    auto_prune_on_merge: bool = True
    memory_limit: str = "4g"
    cpu_limit: float = 2.0

class McpSettings(BaseModel):
    tools_directory: str = "mcp_tools"
    enabled: List[str] = Field(default_factory=lambda: ["datetime_tool", "postgres_inspector", "test_runner"])
    available: List[str] = Field(default_factory=lambda: ["datetime_tool", "postgres_inspector", "test_runner"])

class Preferences(BaseModel):
    harness: HarnessSettings = Field(default_factory=HarnessSettings)
    preparations_step: PreparationsSettings = Field(default_factory=PreparationsSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    docker: DockerSettings = Field(default_factory=DockerSettings)
    mcp_tools: McpSettings = Field(default_factory=McpSettings)

def load_preferences() -> Preferences:
    pref_file = ROOT_DIR / "user_preferences.yaml"
    if pref_file.exists():
        try:
            with open(pref_file, "r") as f:
                data = yaml.safe_load(f) or {}
                return Preferences(**data)
        except Exception as e:
            print(f"[WARN] Error reading user_preferences.yaml: {e}. Using defaults.")
    return Preferences()

# Global settings instance
preferences = load_preferences()

# Environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dbearsong@localhost:5432/hephaestus")
PGHOST = os.getenv("PGHOST", "localhost")
PGPORT = int(os.getenv("PGPORT", 5432))
PGDATABASE = os.getenv("PGDATABASE", "hephaestus")
PGUSER = os.getenv("PGUSER", "dbearsong")
PGPASSWORD = os.getenv("PGPASSWORD", "")

JIRA_SERVER = os.getenv("JIRA_SERVER", "")
JIRA_USERNAME = os.getenv("JIRA_USERNAME", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")
JIRA_WEBHOOK_SECRET = os.getenv("JIRA_WEBHOOK_SECRET", "hephaestus_webhook_secret_2026")

# Provider API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", os.getenv("CLAUDE_API_KEY", ""))
GROK_API_KEY = os.getenv("GROK_API_KEY", os.getenv("XAI_API_KEY", ""))
XAI_API_KEY = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", ""))
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", os.getenv("HF_TOKEN", ""))
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

def get_prompt_output_dir() -> Path:
    """
    Returns the target directory for writing prompt markdown files and staging artifacts.
    Defaults to {project_root}/staging, but can be customized by the user via PROMPT_OUTPUT_DIR in .env.
    """
    custom_dir = os.getenv("PROMPT_OUTPUT_DIR")
    if custom_dir:
        p = Path(custom_dir)
        target = p if p.is_absolute() else ROOT_DIR / p
    else:
        target = ROOT_DIR / "staging"
    target.mkdir(parents=True, exist_ok=True)
    return target

STAGING_DIR = get_prompt_output_dir()
