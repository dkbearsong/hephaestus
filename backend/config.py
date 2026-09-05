import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load root .env
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

class GoogleJulesConfig(BaseModel):
    model: str = "gemini-3.7-flash"
    container_type: str = "google_cloud_workspace"
    auto_execute_tests: bool = True
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "google.com", "pypi.org"])

class GrokBuildConfig(BaseModel):
    model: str = "grok-beta"
    container_type: str = "grok_build_sandbox"
    compiler_mode: str = "ast_parallel"
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "x.ai", "pypi.org"])

class OpenAICodexCloudConfig(BaseModel):
    model: str = "gpt-4o"
    container_type: str = "openai_cloud_sandbox"
    sandbox_timeout_seconds: int = 600
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "openai.com", "pypi.org"])

class DockerSandboxClaudeCodexConfig(BaseModel):
    engine: str = "claude_code" # 'claude_code' | 'openai_codex'
    container_type: str = "docker_sandbox_runner"
    base_image: str = "python:3.12-slim"
    timeout_seconds: int = 600
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "anthropic.com", "openai.com", "pypi.org", "registry.npmjs.org"])

class DevinAIConfig(BaseModel):
    container_type: str = "devin_cloud_session"
    auto_install_dependencies: bool = True
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "cognition.ai", "pypi.org"])

class OpenHandsCanvasConfig(BaseModel):
    runtime_url: str = "http://localhost:3000"
    container_type: str = "openhands_agent_canvas"
    canvas_visualizer: bool = True
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "all-hands.dev", "pypi.org", "registry.npmjs.org"])

class CursorConfig(BaseModel):
    mode: str = "cursor_cloud" # 'cursor_cloud' | 'cursor_dev_container'
    container_type: str = "cursor_cloud_workspace"
    devcontainer_image: str = "mcr.microsoft.com/devcontainers/python:3.12"
    require_approval_for_external_network: bool = True
    allowed_domains: List[str] = Field(default_factory=lambda: ["github.com", "cursor.com", "cursor.sh", "pypi.org", "registry.npmjs.org"])

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
    active: str = "google_jules" # 'google_jules' | 'grok_build' | 'openai_codex_cloud' | 'docker_sandbox_claude_codex' | 'devin_ai' | 'openhands_canvas' | 'cursor_agent' | 'langgraph_agent'
    google_jules: GoogleJulesConfig = Field(default_factory=GoogleJulesConfig)
    grok_build: GrokBuildConfig = Field(default_factory=GrokBuildConfig)
    openai_codex_cloud: OpenAICodexCloudConfig = Field(default_factory=OpenAICodexCloudConfig)
    docker_sandbox_claude_codex: DockerSandboxClaudeCodexConfig = Field(default_factory=DockerSandboxClaudeCodexConfig)
    devin_ai: DevinAIConfig = Field(default_factory=DevinAIConfig)
    openhands_canvas: OpenHandsCanvasConfig = Field(default_factory=OpenHandsCanvasConfig)
    cursor_agent: CursorConfig = Field(default_factory=CursorConfig)
    langgraph_agent: LangGraphConfig = Field(default_factory=LangGraphConfig)

class JiraSettings(BaseModel):
    trigger_label: str = "run_ai_orchestrator"
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

# GitHub Integration Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORGANIZATION = os.getenv("GITHUB_ORGANIZATION", os.getenv("GITHUB_ORG", ""))

# Provider & Agent API Keys
JULES_API_KEY = os.getenv("JULES_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", os.getenv("CLAUDE_API_KEY", ""))
GROK_API_KEY = os.getenv("GROK_API_KEY", os.getenv("XAI_API_KEY", ""))
XAI_API_KEY = os.getenv("XAI_API_KEY", os.getenv("GROK_API_KEY", ""))
DEVIN_API_KEY = os.getenv("DEVIN_API_KEY", "")
CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")
OPENHANDS_RUNTIME_URL = os.getenv("OPENHANDS_RUNTIME_URL", "http://localhost:3000")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", os.getenv("HF_TOKEN", ""))
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

def get_prompt_output_dir() -> Path:
    custom_dir = os.getenv("PROMPT_OUTPUT_DIR")
    if custom_dir:
        p = Path(custom_dir)
        target = p if p.is_absolute() else ROOT_DIR / p
    else:
        target = ROOT_DIR / "staging"
    target.mkdir(parents=True, exist_ok=True)
    return target

STAGING_DIR = get_prompt_output_dir()
