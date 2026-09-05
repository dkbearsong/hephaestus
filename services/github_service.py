"""
GitHub Service for Hephaestus Workspace Orchestrator.
Handles remote repository creation under configured organization/user and remote repository synchronization.
"""

import os
import logging
from typing import Optional, Dict, Any
import httpx

from backend.config import GITHUB_TOKEN, GITHUB_ORGANIZATION

logger = logging.getLogger("hephaestus.services.github")


class GitHubAuthError(Exception):
    """Raised when GitHub token is missing, invalid, or lacks required repository permissions."""
    pass


class GitHubAPIError(Exception):
    """Raised when GitHub API operations fail."""
    pass


class GitHubService:
    def __init__(
        self,
        token: Optional[str] = None,
        organization: Optional[str] = None,
        simulation_mode: bool = False
    ):
        self.token = token if token is not None else GITHUB_TOKEN
        self.organization = organization if organization is not None else GITHUB_ORGANIZATION
        self.simulation_mode = simulation_mode
        self.base_url = "https://api.github.com"

    def is_authenticated(self) -> bool:
        """Returns True if a GitHub token is configured."""
        return bool(self.token and self.token.strip())

    def require_token(self, action: str = "operation") -> None:
        """Fails fast if GitHub token is missing."""
        if not self.is_authenticated() and not self.simulation_mode:
            raise GitHubAuthError(
                f"GitHub authentication token (GITHUB_TOKEN) is missing or empty. "
                f"Cannot proceed with remote GitHub {action}."
            )

    def create_remote_repository(
        self,
        repo_name: str,
        organization: Optional[str] = None,
        private: bool = True,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new remote repository on GitHub under the configured organization
        or authenticated user's account.

        Returns dictionary with:
          - clone_url: e.g. https://github.com/org/name.git
          - full_name: e.g. org/name
          - repo_id: id
        """
        self.require_token("repository creation")

        target_org = organization or self.organization
        desc = description or f"Repository created by Hephaestus for {repo_name}"

        # If in simulation mode or mock testing without live network
        if self.simulation_mode or (self.token and self.token.startswith("mock_")):
            owner = target_org or "mock-org"
            logger.info(f"[SIMULATION] Created simulated remote GitHub repository: {owner}/{repo_name}")
            return {
                "clone_url": f"https://github.com/{owner}/{repo_name}.git",
                "html_url": f"https://github.com/{owner}/{repo_name}",
                "full_name": f"{owner}/{repo_name}",
                "simulated": True
            }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Hephaestus-WorkspaceOrchestrator/2.0"
        }

        payload = {
            "name": repo_name,
            "private": private,
            "description": desc,
            "auto_init": False
        }

        url = f"{self.base_url}/orgs/{target_org}/repos" if target_org else f"{self.base_url}/user/repos"

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 404 and target_org:
                    # target_org was specified, but might be a personal user account rather than an organization
                    user_url = f"{self.base_url}/user/repos"
                    logger.info(f"Org '{target_org}' returned 404; retrying repository creation under user account...")
                    resp = client.post(user_url, json=payload, headers=headers)

                if resp.status_code == 201:
                    data = resp.json()
                    logger.info(f"Successfully created GitHub repository: {data.get('full_name')}")
                    return {
                        "clone_url": data.get("clone_url"),
                        "html_url": data.get("html_url"),
                        "full_name": data.get("full_name"),
                        "simulated": False
                    }
                elif resp.status_code == 422:
                    # Repository might already exist
                    logger.warning(f"Repository {repo_name} already exists or validation error: {resp.text}")
                    owner = target_org or "user"
                    return {
                        "clone_url": f"https://github.com/{owner}/{repo_name}.git",
                        "html_url": f"https://github.com/{owner}/{repo_name}",
                        "full_name": f"{owner}/{repo_name}",
                        "simulated": False
                    }
                elif resp.status_code in (401, 403):
                    raise GitHubAuthError(f"GitHub authentication error ({resp.status_code}): {resp.text}")
                else:
                    raise GitHubAPIError(f"Failed to create GitHub repository ({resp.status_code}): {resp.text}")
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error communicating with GitHub API: {exc}")

    def create_pull_request(
        self,
        repo: str,
        head_branch: str,
        base_branch: str = "main",
        title: Optional[str] = None,
        body: Optional[str] = None,
        draft: bool = False
    ) -> Dict[str, Any]:
        """
        Creates a Pull Request on GitHub for the specified head branch against base branch.
        Supports full 'owner/repo' or simple 'repo' with configured organization.
        """
        self.require_token("pull request creation")

        import re
        repo_match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", repo)
        if repo_match:
            full_repo = f"{repo_match.group(1)}/{repo_match.group(2)}"
        elif "/" in repo:
            full_repo = repo.strip("/")
        else:
            owner = self.organization or "user"
            full_repo = f"{owner}/{repo}"

        pr_title = title or f"Autonomous changes for {head_branch}"
        pr_body = body or f"Automated pull request submitted by Hephaestus agent for branch `{head_branch}`."

        if head_branch == base_branch:
            logger.info(f"Head branch '{head_branch}' matches base branch '{base_branch}'; returning repository root link.")
            return {
                "id": 0,
                "number": 0,
                "html_url": f"https://github.com/{full_repo}",
                "title": f"Repository initialized for {head_branch}",
                "head": head_branch,
                "base": base_branch,
                "state": "initialized",
                "simulated": self.simulation_mode or bool(self.token and self.token.startswith("mock_"))
            }

        if self.simulation_mode or (self.token and self.token.startswith("mock_")):
            logger.info(f"[SIMULATION] Created simulated Pull Request for {full_repo} ({head_branch} -> {base_branch})")
            return {
                "id": 1001,
                "number": 1,
                "html_url": f"https://github.com/{full_repo}/pull/1",
                "title": pr_title,
                "head": head_branch,
                "base": base_branch,
                "state": "open",
                "simulated": True
            }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Hephaestus-WorkspaceOrchestrator/2.0"
        }

        payload = {
            "title": pr_title,
            "head": head_branch,
            "base": base_branch,
            "body": pr_body,
            "draft": draft
        }

        url = f"{self.base_url}/repos/{full_repo}/pulls"

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 201:
                    data = resp.json()
                    logger.info(f"Successfully created GitHub PR #{data.get('number')}: {data.get('html_url')}")
                    return {
                        "id": data.get("id"),
                        "number": data.get("number"),
                        "html_url": data.get("html_url"),
                        "title": data.get("title"),
                        "head": head_branch,
                        "base": base_branch,
                        "state": data.get("state"),
                        "simulated": False
                    }
                elif resp.status_code == 422:
                    # PR might already exist for this branch
                    logger.warning(f"Pull request for {head_branch} may already exist: {resp.text}")
                    list_resp = client.get(f"{url}?head={head_branch}&state=open", headers=headers)
                    if list_resp.status_code == 200 and list_resp.json():
                        existing_pr = list_resp.json()[0]
                        return {
                            "id": existing_pr.get("id"),
                            "number": existing_pr.get("number"),
                            "html_url": existing_pr.get("html_url"),
                            "title": existing_pr.get("title"),
                            "head": head_branch,
                            "base": base_branch,
                            "state": "open",
                            "simulated": False
                        }
                    raise GitHubAPIError(f"GitHub PR validation error: {resp.text}")
                elif resp.status_code in (401, 403):
                    raise GitHubAuthError(f"GitHub authentication error ({resp.status_code}): {resp.text}")
                else:
                    raise GitHubAPIError(f"Failed to create GitHub pull request ({resp.status_code}): {resp.text}")
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error communicating with GitHub API: {exc}")


github_service = GitHubService()
