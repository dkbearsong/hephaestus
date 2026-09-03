"""
Workspace Orchestrator Service
Bridges parser staging directory to downstream agent execution.
"""

from typing import Dict, Any
from backend.workspace_orchestrator.types import PrepSummary, OrchestratorPayload
from backend.workspace_orchestrator.scaffolding import scaffold_workspace
from backend.workspace_orchestrator.provider_prep import prepare_provider
from backend.workspace_orchestrator.prep_agent import run_prep_agent

class WorkspaceOrchestrator:
    def orchestrate(self, payload: Dict[str, Any]) -> PrepSummary:
        scaffold_result = scaffold_workspace(payload)

        prep_result = prepare_provider(
            payload.get("targetPlatform", "LOCAL_CONTAINER"),
            scaffold_result["workingDirectory"],
            payload.get("stagingDir", "")
        )

        prep_summary = run_prep_agent(
            scaffold_result["workingDirectory"],
            scaffold_result["branchName"],
            payload.get("stagingDir", ""),
            prep_result["composedInstructions"]
        )

        return prep_summary

def orchestrate_workspace(payload: Dict[str, Any]) -> PrepSummary:
    orchestrator = WorkspaceOrchestrator()
    return orchestrator.orchestrate(payload)
