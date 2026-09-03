import os
import shutil
import json
import unittest
import subprocess
from backend.workspace_orchestrator import WorkspaceOrchestrator, orchestrate_workspace

TEST_TMP_DIR = os.path.abspath("./tmp_test_python_orchestrator")

class TestWorkspaceOrchestrator(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEST_TMP_DIR):
            shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)
        os.makedirs(TEST_TMP_DIR, exist_ok=True)

    def tearDown(self):
        if os.path.exists(TEST_TMP_DIR):
            shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)

    def test_prompt_new_mode_google_jules(self):
        staging_dir = os.path.join(TEST_TMP_DIR, "staging_1")
        staged_files_dir = os.path.join(staging_dir, "staged_files")
        workspaces_root = os.path.join(TEST_TMP_DIR, "workspaces")

        os.makedirs(staged_files_dir, exist_ok=True)
        os.makedirs(workspaces_root, exist_ok=True)

        with open(os.path.join(staging_dir, "prompt.md"), "w", encoding="utf-8") as f:
            f.write("# Prompt: Add user service\n")
        with open(os.path.join(staging_dir, "preparations.md"), "w", encoding="utf-8") as f:
            f.write("# Preparations\nInstall dependency tsx\n")
        with open(os.path.join(staged_files_dir, "helper.ts"), "w", encoding="utf-8") as f:
            f.write("export const help = () => 'ok';\n")

        payload = {
            "ticketKey": "PROJ-101",
            "mode": "PROMPT_NEW",
            "targetPlatform": "GOOGLE_JULES",
            "repoUrl": None,
            "stagingDir": staging_dir,
            "workspacesRoot": workspaces_root,
        }

        orchestrator = WorkspaceOrchestrator()
        summary = orchestrator.orchestrate(payload)

        self.assertEqual(summary["status"], "READY")
        self.assertEqual(summary["branchName"], "main")
        self.assertTrue(os.path.exists(summary["workingDirectory"]))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], ".gitignore")))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], "README.md")))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], ".jules", "config.json")))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], "helper.ts")))

    def test_prompt_mode_local_container(self):
        remote_repo_dir = os.path.join(TEST_TMP_DIR, "remote_repo")
        os.makedirs(remote_repo_dir, exist_ok=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=remote_repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=remote_repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=remote_repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with open(os.path.join(remote_repo_dir, "package.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"name": "app"}, indent=2))
        subprocess.run(["git", "add", "."], cwd=remote_repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=remote_repo_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        staging_dir = os.path.join(TEST_TMP_DIR, "staging_2")
        staged_files_dir = os.path.join(staging_dir, "staged_files")
        workspaces_root = os.path.join(TEST_TMP_DIR, "workspaces")

        os.makedirs(staged_files_dir, exist_ok=True)
        os.makedirs(workspaces_root, exist_ok=True)

        with open(os.path.join(staging_dir, "prompt.md"), "w", encoding="utf-8") as f:
            f.write("# Prompt\n")
        with open(os.path.join(staging_dir, "preparations.md"), "w", encoding="utf-8") as f:
            f.write("# Prep\n")
        with open(os.path.join(staged_files_dir, "helper.ts"), "w", encoding="utf-8") as f:
            f.write("export const help = () => 'ok';\n")

        payload = {
            "ticketKey": "PROJ-202",
            "mode": "PROMPT",
            "targetPlatform": "LOCAL_CONTAINER",
            "repoUrl": remote_repo_dir,
            "stagingDir": staging_dir,
            "workspacesRoot": workspaces_root,
        }

        summary = orchestrate_workspace(payload)

        self.assertEqual(summary["status"], "READY")
        self.assertEqual(summary["branchName"], "jira-PROJ-202-agent")
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], ".docker_mounts.json")))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], ".env")))
        self.assertTrue(os.path.exists(os.path.join(summary["workingDirectory"], "src", "helper.ts")))

    def test_codex_cloud_platform(self):
        staging_dir = os.path.join(TEST_TMP_DIR, "staging_3")
        workspaces_root = os.path.join(TEST_TMP_DIR, "workspaces")

        os.makedirs(staging_dir, exist_ok=True)
        os.makedirs(workspaces_root, exist_ok=True)

        payload = {
            "ticketKey": "PROJ-303",
            "mode": "PROMPT_NEW",
            "targetPlatform": "CODEX_CLOUD",
            "repoUrl": None,
            "stagingDir": staging_dir,
            "workspacesRoot": workspaces_root,
        }

        summary = orchestrate_workspace(payload)

        self.assertEqual(summary["status"], "READY")
        metadata_path = os.path.join(summary["workingDirectory"], ".codex", "task_metadata.json")
        self.assertTrue(os.path.exists(metadata_path))

    def test_blocked_preparation(self):
        staging_dir = os.path.join(TEST_TMP_DIR, "staging_4")
        workspaces_root = os.path.join(TEST_TMP_DIR, "workspaces")

        os.makedirs(staging_dir, exist_ok=True)
        os.makedirs(workspaces_root, exist_ok=True)

        with open(os.path.join(staging_dir, "prompt.md"), "w", encoding="utf-8") as f:
            f.write("# Prompt\n")
        with open(os.path.join(staging_dir, "preparations.md"), "w", encoding="utf-8") as f:
            f.write("STATUS: BLOCKED\nMissing mandatory keys\n")

        payload = {
            "ticketKey": "PROJ-404",
            "mode": "PROMPT_NEW",
            "targetPlatform": "GOOGLE_JULES",
            "repoUrl": None,
            "stagingDir": staging_dir,
            "workspacesRoot": workspaces_root,
        }

        summary = orchestrate_workspace(payload)

        self.assertEqual(summary["status"], "BLOCKED")
        self.assertIsNotNone(summary.get("blockerReason"))

if __name__ == "__main__":
    unittest.main()
