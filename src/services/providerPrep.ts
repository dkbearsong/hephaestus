import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";
import { TargetPlatform, ProviderPrepResult } from "../types.js";

/**
 * Dynamic Provider Preparation Engine
 */
export async function prepareProvider(
  targetPlatform: TargetPlatform,
  workingDirectory: string,
  stagingDir: string
): Promise<ProviderPrepResult> {
  const platformConfigs: Record<string, string> = {};
  const platformRules: string[] = [];

  // 1. Target platform specific configuration logic
  switch (targetPlatform) {
    case "GOOGLE_JULES": {
      // Enforce zero uncommitted files rule
      platformRules.push("PROVIDER RULE (GOOGLE_JULES): Zero uncommitted files requirement enforced.");
      platformRules.push("PROVIDER RULE (GOOGLE_JULES): Ensure .jules/ configuration is present and updated.");
      platformRules.push("PROVIDER RULE (GOOGLE_JULES): Set build and test hooks into standard repo configs.");

      // Generate/update .jules/ configuration
      const julesDir = path.join(workingDirectory, ".jules");
      if (!fs.existsSync(julesDir)) {
        fs.mkdirSync(julesDir, { recursive: true });
      }

      const julesConfigPath = path.join(julesDir, "config.json");
      let existingJulesConfig: Record<string, unknown> = {};
      if (fs.existsSync(julesConfigPath)) {
        try {
          existingJulesConfig = JSON.parse(fs.readFileSync(julesConfigPath, "utf-8"));
        } catch {
          existingJulesConfig = {};
        }
      }

      const updatedJulesConfig = {
        ...existingJulesConfig,
        provider: "GOOGLE_JULES",
        hooks: {
          build: "npm run build",
          test: "npm test",
        },
        enforceZeroUncommitted: true,
        lastUpdated: new Date().toISOString(),
      };

      const julesConfigStr = JSON.stringify(updatedJulesConfig, null, 2);
      fs.writeFileSync(julesConfigPath, julesConfigStr, "utf-8");
      platformConfigs[".jules/config.json"] = julesConfigStr;

      // Commit any configuration changes if in git repo to enforce zero uncommitted files
      try {
        execSync("git add .jules/", { cwd: workingDirectory, stdio: "pipe" });
        execSync('git commit -m "Configure GOOGLE_JULES platform settings"', {
          cwd: workingDirectory,
          stdio: "pipe",
        });
      } catch {
        // ignore if git commit fails (e.g. no changes)
      }
      break;
    }

    case "CODEX_CLOUD": {
      platformRules.push("PROVIDER RULE (CODEX_CLOUD): Verify top-level execution entry points.");
      platformRules.push("PROVIDER RULE (CODEX_CLOUD): Format task metadata for GitHub App webhook trigger.");

      const codexDir = path.join(workingDirectory, ".codex");
      if (!fs.existsSync(codexDir)) {
        fs.mkdirSync(codexDir, { recursive: true });
      }

      const metadataPath = path.join(codexDir, "task_metadata.json");
      const metadata = {
        provider: "CODEX_CLOUD",
        webhookTriggered: true,
        entryPoints: ["src/index.js", "src/index.ts", "index.js", "main.py", "package.json"],
        configuredAt: new Date().toISOString(),
      };

      const metadataStr = JSON.stringify(metadata, null, 2);
      fs.writeFileSync(metadataPath, metadataStr, "utf-8");
      platformConfigs[".codex/task_metadata.json"] = metadataStr;
      break;
    }

    case "LOCAL_CONTAINER": {
      platformRules.push("PROVIDER RULE (LOCAL_CONTAINER): Configure Docker mount points.");
      platformRules.push("PROVIDER RULE (LOCAL_CONTAINER): Export .env variables from staged configs.");
      platformRules.push("PROVIDER RULE (LOCAL_CONTAINER): Ensure execute permissions on scripts.");

      // Configure Docker mount points in .docker_mounts.json or similar
      const dockerMounts = {
        workspace: workingDirectory,
        mountPoints: [
          { host: workingDirectory, container: "/workspace", mode: "rw" },
        ],
      };
      const mountsStr = JSON.stringify(dockerMounts, null, 2);
      fs.writeFileSync(path.join(workingDirectory, ".docker_mounts.json"), mountsStr, "utf-8");
      platformConfigs[".docker_mounts.json"] = mountsStr;

      // Export .env variables from staged configs if staged .env or preparations exists
      const stagedEnvPath = path.join(stagingDir, "staged_files", ".env");
      let envContent = "ENVIRONMENT=LOCAL_CONTAINER\n";
      if (fs.existsSync(stagedEnvPath)) {
        envContent += fs.readFileSync(stagedEnvPath, "utf-8") + "\n";
      }
      fs.writeFileSync(path.join(workingDirectory, ".env"), envContent, "utf-8");
      platformConfigs[".env"] = envContent;

      // Ensure execution permissions (chmod +x) on shell scripts in working directory
      if (fs.existsSync(workingDirectory)) {
        const entries = fs.readdirSync(workingDirectory);
        for (const entry of entries) {
          if (entry.endsWith(".sh")) {
            const scriptPath = path.join(workingDirectory, entry);
            try {
              fs.chmodSync(scriptPath, 0o755);
            } catch {
              // ignore on non-posix if applicable
            }
          }
        }
      }
      break;
    }
  }

  // 2. Read user's preparations.md from stagingDir
  let preparationsMd = "";
  const prepPath = path.join(stagingDir, "preparations.md");
  if (fs.existsSync(prepPath)) {
    preparationsMd = fs.readFileSync(prepPath, "utf-8");
  }

  // 3. Compose prompt payload for the Preparation Agent
  const composedInstructions = [
    "=== TARGET PLATFORM CONSTRAINTS ===",
    ...platformRules,
    "",
    "=== USER PREPARATIONS INSTRUCTIONS ===",
    preparationsMd || "(No specific preparations.md provided)",
  ].join("\n");

  return {
    composedInstructions,
    platformConfigs,
  };
}
