import * as fs from "fs";
import * as path from "path";
import { copyRecursiveSync } from "./scaffolding.js";
import { PrepSummary, DetectedCommands } from "../types.js";

function getDirectoryTree(dir: string, baseDir: string = dir): string[] {
  let fileList: string[] = [];
  if (!fs.existsSync(dir)) return fileList;

  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.name === ".git" || entry.name === "node_modules") continue;
    const fullPath = path.join(dir, entry.name);
    const relPath = path.relative(baseDir, fullPath);
    if (entry.isDirectory()) {
      fileList.push(`${relPath}/`);
      fileList = fileList.concat(getDirectoryTree(fullPath, baseDir));
    } else {
      fileList.push(relPath);
    }
  }
  return fileList;
}

/**
 * Preparation Agent Integration
 */
export async function runPrepAgent(params: {
  workingDirectory: string;
  branchName: string;
  stagingDir: string;
  composedInstructions: string;
}): Promise<PrepSummary> {
  const { workingDirectory, branchName, stagingDir, composedInstructions } = params;
  const filesModified: string[] = [];

  // 1. Read workspace file tree
  const _workspaceTree = getDirectoryTree(workingDirectory);

  // 2. Read prompt.md if present
  let promptMd = "";
  const promptPath = path.join(stagingDir, "prompt.md");
  if (fs.existsSync(promptPath)) {
    promptMd = fs.readFileSync(promptPath, "utf-8");
  }

  // 3. Move any staged or inbox files to their intended module paths
  const inboxDir = path.join(workingDirectory, ".harness_inbox");
  if (fs.existsSync(inboxDir)) {
    const inboxItems = fs.readdirSync(inboxDir);
    for (const item of inboxItems) {
      const srcPath = path.join(inboxDir, item);
      let targetSubdir = "";

      // Determine target path based on file extension/type or instructions
      if (item.endsWith(".ts") || item.endsWith(".js") || item.endsWith(".jsx") || item.endsWith(".tsx")) {
        targetSubdir = "src";
      } else if (item.endsWith(".py")) {
        targetSubdir = "app";
      } else {
        targetSubdir = "config";
      }

      const destDir = path.join(workingDirectory, targetSubdir);
      if (!fs.existsSync(destDir)) {
        fs.mkdirSync(destDir, { recursive: true });
      }

      const destPath = path.join(destDir, item);
      copyRecursiveSync(srcPath, destPath);
      const relDest = path.relative(workingDirectory, destPath);
      filesModified.push(relDest);

      // Clean up inbox item
      try {
        fs.rmSync(srcPath, { recursive: true, force: true });
      } catch {
        // ignore
      }
    }

    // Clean up empty .harness_inbox directory
    try {
      if (fs.readdirSync(inboxDir).length === 0) {
        fs.rmdirSync(inboxDir);
      }
    } catch {
      // ignore
    }
  }

  // 4. Update project dependency declarations or build scripts if indicated by preparations.md
  const detectedCommands: DetectedCommands = {};

  const pkgJsonPath = path.join(workingDirectory, "package.json");
  if (fs.existsSync(pkgJsonPath)) {
    detectedCommands.build = "npm run build";
    detectedCommands.test = "npm test";
    detectedCommands.lint = "npm run lint";

    // If preparations or prompt indicates dependency updates
    if (
      composedInstructions.toLowerCase().includes("dependency") ||
      composedInstructions.toLowerCase().includes("install") ||
      promptMd.toLowerCase().includes("dependency")
    ) {
      try {
        const pkgData = JSON.parse(fs.readFileSync(pkgJsonPath, "utf-8"));
        pkgData.scripts = pkgData.scripts || {};
        if (!pkgData.scripts.build) pkgData.scripts.build = "tsc";
        if (!pkgData.scripts.test) pkgData.scripts.test = "node --test";

        fs.writeFileSync(pkgJsonPath, JSON.stringify(pkgData, null, 2), "utf-8");
        if (!filesModified.includes("package.json")) {
          filesModified.push("package.json");
        }
      } catch {
        // ignore JSON parse error
      }
    }
  } else {
    // Check python/other project files
    if (fs.existsSync(path.join(workingDirectory, "requirements.txt")) || fs.existsSync(path.join(workingDirectory, "pytest.ini"))) {
      detectedCommands.test = "pytest";
      detectedCommands.lint = "flake8";
    }
  }

  // Check for blocker conditions (e.g. instructions explicitly stating BLOCKED or missing required inputs)
  if (composedInstructions.includes("STATUS: BLOCKED") || promptMd.includes("STATUS: BLOCKED")) {
    return {
      status: "BLOCKED",
      workingDirectory,
      branchName,
      detectedCommands,
      filesModified,
      blockerReason: "Blocked by preparations directive or missing required dependency setup",
    };
  }

  // CRITICAL RULE: Never write the actual feature code requested in prompt.md.
  // The preparation agent ONLY sets up files, directories, dependency configs, and build scripts.

  return {
    status: "READY",
    workingDirectory,
    branchName,
    detectedCommands,
    filesModified,
  };
}
