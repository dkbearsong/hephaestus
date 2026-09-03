export type OrchestratorMode = "PROMPT_NEW" | "PROMPT";

export type TargetPlatform = "GOOGLE_JULES" | "CODEX_CLOUD" | "LOCAL_CONTAINER";

export interface OrchestratorPayload {
  ticketKey: string;
  mode: OrchestratorMode;
  targetPlatform: TargetPlatform;
  repoUrl: string | null;
  stagingDir: string;
  workspacesRoot: string;
  githubToken?: string;
}

export interface DetectedCommands {
  build?: string;
  test?: string;
  lint?: string;
}

export interface PrepSummary {
  status: "READY" | "BLOCKED";
  workingDirectory: string;
  branchName: string;
  detectedCommands: DetectedCommands;
  filesModified: string[];
  blockerReason?: string;
}

export interface ProviderPrepResult {
  composedInstructions: string;
  platformConfigs: Record<string, string>;
}
