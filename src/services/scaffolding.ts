import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import { OrchestratorPayload } from "../types.js";

const DEFAULT_GITIGNORE = `# Dependencies
node_modules/
.venv/
venv/
__pycache__/

# Build outputs
dist/
build/
*.so

# Environment & local files
.env
.env.local
.DS_Store
`;

const DEFAULT_README = `# Project Workspace

Auto-scaffolded workspace for Jira ticket task.
`;

const DEFAULT_LICENSE = `MIT License

Copyright (c) ${new Date().getFullYear()}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to do so.
`;

/**
 * Copies a file or directory recursively from src to dest.
 */
export function copyRecursiveSync(src: string, dest: string): void {
  if (!fs.existsSync(src)) return;
  const stats = fs.statSync(src);
  if (stats.isDirectory()) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    const entries = fs.readdirSync(src);
    for (const entry of entries) {
      copyRecursiveSync(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    const parent = path.dirname(dest);
    if (!fs.existsSync(parent)) {
      fs.mkdirSync(parent, { recursive: true });
    }
    fs.copyFileSync(src, dest);
  }
}

export interface ScaffoldResult {
  workingDirectory: string;
  branchName: string;
  stagedFilesCopied: string[];
}

/**
 * Deterministic Scaffolding Engine
 */
export async function scaffoldWorkspace(
  payload: OrchestratorPayload
): Promise<ScaffoldResult> {
  const timestamp = Date.now();
  const workingDirectory = path.resolve(
    payload.workspacesRoot,
    `${payload.ticketKey}_${timestamp}`
  );

  if (!fs.existsSync(workingDirectory)) {
    fs.mkdirSync(workingDirectory, { recursive: true });
  }

  const stagedFilesDir = path.join(payload.stagingDir, "staged_files");
  const stagedFilesCopied: string[] = [];

  if (payload.mode === "PROMPT_NEW") {
    // 1. Run git init -b main
    try {
      execSync("git init -b main", { cwd: workingDirectory, stdio: "pipe" });
    } catch {
      // Fallback if git version doesn't support -b
      execSync("git init", { cwd: workingDirectory, stdio: "pipe" });
      execSync("git checkout -b main", { cwd: workingDirectory, stdio: "pipe" });
    }

    // Configure local git committer if not set
    try {
      execSync('git config user.name "Hephaestus Agent"', { cwd: workingDirectory, stdio: "pipe" });
      execSync('git config user.email "agent@hephaestus.local"', { cwd: workingDirectory, stdio: "pipe" });
    } catch {
      // ignore
    }

    // 2. Unpack base starter template
    const gitignorePath = path.join(workingDirectory, ".gitignore");
    if (!fs.existsSync(gitignorePath)) {
      fs.writeFileSync(gitignorePath, DEFAULT_GITIGNORE, "utf-8");
    }

    const readmePath = path.join(workingDirectory, "README.md");
    if (!fs.existsSync(readmePath)) {
      fs.writeFileSync(readmePath, DEFAULT_README, "utf-8");
    }

    const licensePath = path.join(workingDirectory, "LICENSE");
    if (!fs.existsSync(licensePath)) {
      fs.writeFileSync(licensePath, DEFAULT_LICENSE, "utf-8");
    }

    // 3. Inject target platform baseline configurations if applicable
    if (payload.targetPlatform === "GOOGLE_JULES") {
      const julesDir = path.join(workingDirectory, ".jules");
      if (!fs.existsSync(julesDir)) {
        fs.mkdirSync(julesDir, { recursive: true });
      }
      fs.writeFileSync(
        path.join(julesDir, "config.json"),
        JSON.stringify({ ticketKey: payload.ticketKey, created: new Date().toISOString() }, null, 2),
        "utf-8"
      );
    } else if (payload.targetPlatform === "CODEX_CLOUD") {
      const codexDir = path.join(workingDirectory, ".codex");
      if (!fs.existsSync(codexDir)) {
        fs.mkdirSync(codexDir, { recursive: true });
      }
      fs.writeFileSync(
        path.join(codexDir, "instructions.md"),
        `# Codex Cloud Instructions for ${payload.ticketKey}\n`,
        "utf-8"
      );
    } else if (payload.targetPlatform === "LOCAL_CONTAINER") {
      const envPath = path.join(workingDirectory, ".env.example");
      if (!fs.existsSync(envPath)) {
        fs.writeFileSync(envPath, `TICKET_KEY=${payload.ticketKey}\n`, "utf-8");
      }
    }

    // 4. Copy all assets from ${stagingDir}/staged_files/ directly into workspace root
    if (fs.existsSync(stagedFilesDir)) {
      const files = fs.readdirSync(stagedFilesDir);
      for (const file of files) {
        const srcPath = path.join(stagedFilesDir, file);
        const destPath = path.join(workingDirectory, file);
        copyRecursiveSync(srcPath, destPath);
        stagedFilesCopied.push(file);
      }
    }

    // Initial commit for git tracking
    try {
      execSync("git add .", { cwd: workingDirectory, stdio: "pipe" });
      execSync('git commit -m "Initial commit from starter template and staged files"', {
        cwd: workingDirectory,
        stdio: "pipe",
      });
    } catch {
      // ignore empty git commit error if nothing to commit
    }

    return {
      workingDirectory,
      branchName: "main",
      stagedFilesCopied,
    };
  } else {
    // Mode === 'PROMPT'
    let cloneUrl = payload.repoUrl || "";
    if (payload.githubToken && cloneUrl.startsWith("https://github.com/")) {
      const urlBody = cloneUrl.replace("https://github.com/", "");
      cloneUrl = `https://x-access-token:${payload.githubToken}@github.com/${urlBody}`;
    }

    if (cloneUrl) {
      execSync(`git clone "${cloneUrl}" "${workingDirectory}"`, { stdio: "pipe" });
    } else {
      // Fallback if local testing repo without remote
      execSync("git init", { cwd: workingDirectory, stdio: "pipe" });
    }

    // Configure local git committer if not set
    try {
      execSync('git config user.name "Hephaestus Agent"', { cwd: workingDirectory, stdio: "pipe" });
      execSync('git config user.email "agent@hephaestus.local"', { cwd: workingDirectory, stdio: "pipe" });
    } catch {
      // ignore
    }

    // Create and checkout tracking branch
    const branchName = `jira-${payload.ticketKey}-agent`;
    try {
      execSync(`git checkout -b ${branchName}`, { cwd: workingDirectory, stdio: "pipe" });
    } catch {
      // If branch already exists or checkout fails
      execSync(`git checkout ${branchName}`, { cwd: workingDirectory, stdio: "pipe" });
    }

    // Copy any assets from ${stagingDir}/staged_files/ into .harness_inbox/
    const inboxDir = path.join(workingDirectory, ".harness_inbox");
    if (!fs.existsSync(inboxDir)) {
      fs.mkdirSync(inboxDir, { recursive: true });
    }

    if (fs.existsSync(stagedFilesDir)) {
      const files = fs.readdirSync(stagedFilesDir);
      for (const file of files) {
        const srcPath = path.join(stagedFilesDir, file);
        const destPath = path.join(inboxDir, file);
        copyRecursiveSync(srcPath, destPath);
        stagedFilesCopied.push(`.harness_inbox/${file}`);
      }
    }

    return {
      workingDirectory,
      branchName,
      stagedFilesCopied,
    };
  }
}
