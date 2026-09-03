import { OrchestratorPayload, PrepSummary } from "../types.js";
import { scaffoldWorkspace } from "./scaffolding.js";
import { prepareProvider } from "./providerPrep.js";
import { runPrepAgent } from "./prepAgent.js";

export class WorkspaceOrchestrator {
  /**
   * Orchestrates the complete workflow:
   * 1. Deterministic Scaffolding Engine
   * 2. Dynamic Provider Preparation Engine
   * 3. Preparation Agent Integration
   */
  public async orchestrate(payload: OrchestratorPayload): Promise<PrepSummary> {
    // Step 1: Deterministic Scaffolding Engine
    const scaffoldResult = await scaffoldWorkspace(payload);

    // Step 2: Dynamic Provider Preparation Engine
    const prepResult = await prepareProvider(
      payload.targetPlatform,
      scaffoldResult.workingDirectory,
      payload.stagingDir
    );

    // Step 3: Preparation Agent Integration
    const prepSummary = await runPrepAgent({
      workingDirectory: scaffoldResult.workingDirectory,
      branchName: scaffoldResult.branchName,
      stagingDir: payload.stagingDir,
      composedInstructions: prepResult.composedInstructions,
    });

    return prepSummary;
  }
}

export async function orchestrateWorkspace(
  payload: OrchestratorPayload
): Promise<PrepSummary> {
  const orchestrator = new WorkspaceOrchestrator();
  return orchestrator.orchestrate(payload);
}
