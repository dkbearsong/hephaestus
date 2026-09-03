import test from "node:test";
import assert from "node:assert/strict";
import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import { WorkspaceOrchestrator } from "../src/services/workspaceOrchestrator.js";
import { OrchestratorPayload } from "../src/types.js";

const TEST_DIR = path.resolve("./tmp_test_orchestrator");

function setupTestEnvironment() {
  if (fs.existsSync(TEST_DIR)) {
    fs.rmSync(TEST_DIR, { recursive: true, force: true });
  }
  fs.mkdirSync(TEST_DIR, { recursive: true });
}

function cleanupTestEnvironment() {
  if (fs.existsSync(TEST_DIR)) {
    fs.rmSync(TEST_DIR, { recursive: true, force: true });
  }
}

test("1. PROMPT_NEW mode with GOOGLE_JULES platform", async () => {
  setupTestEnvironment();
  try {
    const stagingDir = path.join(TEST_DIR, "staging_proj1");
    const stagedFilesDir = path.join(stagingDir, "staged_files");
    const workspacesRoot = path.join(TEST_DIR, "workspaces");

    fs.mkdirSync(stagedFilesDir, { recursive: true });
    fs.mkdirSync(workspacesRoot, { recursive: true });

    fs.writeFileSync(path.join(stagingDir, "prompt.md"), "# Feature Prompt: Add user service\n");
    fs.writeFileSync(
      path.join(stagingDir, "preparations.md"),
      "# Preparations\nInstall dependency tsx and update package.json\n"
    );
    fs.writeFileSync(path.join(stagedFilesDir, "helper.ts"), "export const help = () => 'ok';\n");

    const payload: OrchestratorPayload = {
      ticketKey: "PROJ-101",
      mode: "PROMPT_NEW",
      targetPlatform: "GOOGLE_JULES",
      repoUrl: null,
      stagingDir,
      workspacesRoot,
    };

    const orchestrator = new WorkspaceOrchestrator();
    const summary = await orchestrator.orchestrate(payload);

    assert.equal(summary.status, "READY");
    assert.equal(summary.branchName, "main");
    assert.ok(fs.existsSync(summary.workingDirectory));
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, ".gitignore")));
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, "README.md")));
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, "LICENSE")));
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, ".jules", "config.json")));

    const julesConfig = JSON.parse(
      fs.readFileSync(path.join(summary.workingDirectory, ".jules", "config.json"), "utf-8")
    );
    assert.equal(julesConfig.provider, "GOOGLE_JULES");
    assert.equal(julesConfig.enforceZeroUncommitted, true);

    // In PROMPT_NEW mode, staged files are copied directly into workspace root
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, "helper.ts")));
  } finally {
    cleanupTestEnvironment();
  }
});

test("2. PROMPT mode with LOCAL_CONTAINER platform", async () => {
  setupTestEnvironment();
  try {
    // Create a dummy remote repo directory to clone from
    const remoteRepoDir = path.join(TEST_DIR, "remote_repo");
    fs.mkdirSync(remoteRepoDir, { recursive: true });
    execSync("git init -b main", { cwd: remoteRepoDir, stdio: "pipe" });
    execSync('git config user.name "Test"', { cwd: remoteRepoDir, stdio: "pipe" });
    execSync('git config user.email "test@test.com"', { cwd: remoteRepoDir, stdio: "pipe" });
    fs.writeFileSync(path.join(remoteRepoDir, "package.json"), JSON.stringify({ name: "my-app" }, null, 2));
    execSync("git add . && git commit -m 'initial'", { cwd: remoteRepoDir, stdio: "pipe" });

    const stagingDir = path.join(TEST_DIR, "staging_proj2");
    const stagedFilesDir = path.join(stagingDir, "staged_files");
    const workspacesRoot = path.join(TEST_DIR, "workspaces");

    fs.mkdirSync(stagedFilesDir, { recursive: true });
    fs.mkdirSync(workspacesRoot, { recursive: true });

    fs.writeFileSync(path.join(stagingDir, "prompt.md"), "# Feature Prompt: Add feature X\n");
    fs.writeFileSync(path.join(stagingDir, "preparations.md"), "# Preparations\nSet up local environment\n");
    fs.writeFileSync(path.join(stagedFilesDir, "helper.ts"), "export const help = () => 'ok';\n");

    const payload: OrchestratorPayload = {
      ticketKey: "PROJ-202",
      mode: "PROMPT",
      targetPlatform: "LOCAL_CONTAINER",
      repoUrl: remoteRepoDir,
      stagingDir,
      workspacesRoot,
    };

    const orchestrator = new WorkspaceOrchestrator();
    const summary = await orchestrator.orchestrate(payload);

    assert.equal(summary.status, "READY");
    assert.equal(summary.branchName, "jira-PROJ-202-agent");
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, ".docker_mounts.json")));
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, ".env")));
    // In PROMPT mode, staged files in .harness_inbox are relocated by prepAgent to src/
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, "src", "helper.ts")));
  } finally {
    cleanupTestEnvironment();
  }
});

test("3. CODEX_CLOUD platform provider prep test", async () => {
  setupTestEnvironment();
  try {
    const stagingDir = path.join(TEST_DIR, "staging_proj3");
    const workspacesRoot = path.join(TEST_DIR, "workspaces");

    fs.mkdirSync(stagingDir, { recursive: true });
    fs.mkdirSync(workspacesRoot, { recursive: true });

    fs.writeFileSync(path.join(stagingDir, "prompt.md"), "# Prompt\n");
    fs.writeFileSync(path.join(stagingDir, "preparations.md"), "# Prep\n");

    const payload: OrchestratorPayload = {
      ticketKey: "PROJ-303",
      mode: "PROMPT_NEW",
      targetPlatform: "CODEX_CLOUD",
      repoUrl: null,
      stagingDir,
      workspacesRoot,
    };

    const summary = await new WorkspaceOrchestrator().orchestrate(payload);

    assert.equal(summary.status, "READY");
    assert.ok(fs.existsSync(path.join(summary.workingDirectory, ".codex", "task_metadata.json")));

    const metadata = JSON.parse(
      fs.readFileSync(path.join(summary.workingDirectory, ".codex", "task_metadata.json"), "utf-8")
    );
    assert.equal(metadata.provider, "CODEX_CLOUD");
    assert.equal(metadata.webhookTriggered, true);
  } finally {
    cleanupTestEnvironment();
  }
});

test("4. Blocked preparation status test", async () => {
  setupTestEnvironment();
  try {
    const stagingDir = path.join(TEST_DIR, "staging_proj4");
    const workspacesRoot = path.join(TEST_DIR, "workspaces");

    fs.mkdirSync(stagingDir, { recursive: true });
    fs.mkdirSync(workspacesRoot, { recursive: true });

    fs.writeFileSync(path.join(stagingDir, "prompt.md"), "# Prompt\n");
    fs.writeFileSync(path.join(stagingDir, "preparations.md"), "STATUS: BLOCKED\nMissing mandatory API keys.\n");

    const payload: OrchestratorPayload = {
      ticketKey: "PROJ-404",
      mode: "PROMPT_NEW",
      targetPlatform: "GOOGLE_JULES",
      repoUrl: null,
      stagingDir,
      workspacesRoot,
    };

    const summary = await new WorkspaceOrchestrator().orchestrate(payload);

    assert.equal(summary.status, "BLOCKED");
    assert.ok(summary.blockerReason);
  } finally {
    cleanupTestEnvironment();
  }
});
