"""
Types and data structures for Workspace Orchestrator
"""

from typing import Literal, Optional, List, Dict, Any, TypedDict

OrchestratorMode = Literal["PROMPT_NEW", "PROMPT"]
TargetPlatform = Literal["GOOGLE_JULES", "CODEX_CLOUD", "LOCAL_CONTAINER"]

class OrchestratorPayload(TypedDict, total=False):
    ticketKey: str
    mode: OrchestratorMode
    targetPlatform: TargetPlatform
    repoUrl: Optional[str]
    stagingDir: str
    workspacesRoot: str
    githubToken: Optional[str]

class DetectedCommands(TypedDict, total=False):
    build: Optional[str]
    test: Optional[str]
    lint: Optional[str]

class PrepSummary(TypedDict, total=False):
    status: Literal["READY", "BLOCKED"]
    workingDirectory: str
    branchName: str
    detectedCommands: DetectedCommands
    filesModified: List[str]
    blockerReason: Optional[str]

class ScaffoldResult(TypedDict):
    workingDirectory: str
    branchName: str
    stagedFilesCopied: List[str]

class ProviderPrepResult(TypedDict):
    composedInstructions: str
    platformConfigs: Dict[str, str]
