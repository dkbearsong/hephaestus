"""
GitHub Service for Hephaestus Workspace Orchestrator.
Handles remote repository creation under configured organization/user and remote repository synchronization.
"""

import os
import re
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


class GitHubRepoNotFoundError(GitHubAPIError):
    """
    Raised when the repository itself cannot be resolved through the GitHub API
    (404 - it does not exist, or the token cannot see it).
    """
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

    @staticmethod
    def _normalize_repo(repo: str) -> str:
        """Normalizes 'owner/name', full GitHub URLs, or git@ URLs into 'owner/name'."""
        cleaned = (repo or "").strip()
        if not cleaned:
            raise GitHubAPIError("Repository coordinates are required for GitHub branch operations.")
        if "@" in cleaned:
            # e.g. git@github.com:owner/name.git
            cleaned = cleaned.split("@", 1)[1].replace(":", "/", 1)
        if "://" in cleaned:
            cleaned = cleaned.split("://", 1)[1].split("/", 1)[-1]
        cleaned = cleaned.strip("/")
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]
        parts = [segment for segment in cleaned.split("/") if segment]
        if len(parts) < 2:
            raise GitHubAPIError(f"Could not resolve 'owner/repo' coordinates from '{repo}'.")
        return f"{parts[-2]}/{parts[-1]}"

    def _branch_headers(self) -> Dict[str, str]:
        """Standard authenticated headers for GitHub branch/ref operations."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Hephaestus-WorkspaceOrchestrator/2.0"
        }

    def _is_simulated(self) -> bool:
        """Returns True when GitHub calls are mocked (simulation mode or mock token)."""
        return self.simulation_mode or bool(self.token and self.token.startswith("mock_"))

    def get_branch(self, repo: str, branch: str) -> Optional[Dict[str, Any]]:
        """
        Returns branch metadata for the given repository, or None when the branch
        does not exist (HTTP 404).

        Accepts 'owner/name' or a full GitHub repository URL.
        """
        self.require_token("branch verification")
        full_repo = self._normalize_repo(repo)

        if self._is_simulated():
            logger.info(f"[SIMULATION] Verified simulated branch {full_repo}#{branch}")
            return {
                "name": branch,
                "sha": "simulated_sha",
                "protected": False,
                "simulated": True
            }

        url = f"{self.base_url}/repos/{full_repo}/branches/{branch}"

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, headers=self._branch_headers())
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error verifying branch '{branch}' in {full_repo}: {exc}")

        if resp.status_code == 200:
            data = resp.json()
            return {
                "name": data.get("name", branch),
                "sha": (data.get("commit") or {}).get("sha"),
                "protected": bool(data.get("protected")),
                "simulated": False
            }
        if resp.status_code == 404:
            logger.info(f"GitHub branch not found: {full_repo}#{branch}")
            return None
        if resp.status_code in (401, 403):
            raise GitHubAuthError(f"GitHub authentication error ({resp.status_code}): {resp.text}")
        raise GitHubAPIError(
            f"Failed to verify branch '{branch}' in {full_repo} ({resp.status_code}): {resp.text}"
        )

    def _fetch_ref_sha(
        self,
        client: httpx.Client,
        full_repo: str,
        branch: str,
        headers: Dict[str, str]
    ) -> Optional[str]:
        """Resolves the commit SHA of a single branch ref, or None when it is absent."""
        resp = client.get(
            f"{self.base_url}/repos/{full_repo}/git/ref/heads/{branch}",
            headers=headers
        )
        if resp.status_code == 200:
            return (resp.json().get("object") or {}).get("sha")
        if resp.status_code in (401, 403):
            raise GitHubAuthError(f"GitHub authentication error ({resp.status_code}): {resp.text}")
        return None

    def _resolve_base_sha(self, full_repo: str, base_branch: str) -> Optional[str]:
        """
        Resolves the commit SHA to branch from: prefers `base_branch`, then falls
        back to the repository's default branch.

        Raises GitHubRepoNotFoundError when the repository itself is not resolvable,
        which is distinct from "the repository exists but the base branch is missing".
        """
        headers = self._branch_headers()

        try:
            with httpx.Client(timeout=20.0) as client:
                base_sha = self._fetch_ref_sha(client, full_repo, base_branch, headers)
                if base_sha:
                    return base_sha

                repo_resp = client.get(f"{self.base_url}/repos/{full_repo}", headers=headers)
                if repo_resp.status_code in (401, 403):
                    raise GitHubAuthError(
                        f"GitHub authentication error ({repo_resp.status_code}): {repo_resp.text}"
                    )
                if repo_resp.status_code == 404:
                    raise GitHubRepoNotFoundError(
                        f"Repository '{full_repo}' is not resolvable through the GitHub API "
                        f"(it may not exist, or the token cannot access it)."
                    )
                if repo_resp.status_code == 200:
                    default_branch = repo_resp.json().get("default_branch")
                    if default_branch and default_branch != base_branch:
                        logger.info(
                            f"Base branch '{base_branch}' missing in {full_repo}; "
                            f"falling back to default branch '{default_branch}'."
                        )
                        return self._fetch_ref_sha(client, full_repo, default_branch, headers)
        except httpx.RequestError as exc:
            raise GitHubAPIError(
                f"Network error resolving base branch '{base_branch}' in {full_repo}: {exc}"
            )

        return None


    def ensure_branch(
        self,
        repo: str,
        branch: str,
        base_branch: str = "main",
        create_if_missing: bool = True,
        allow_unverifiable: bool = False
    ) -> Dict[str, Any]:
        """
        Guarantees that a target branch exists on GitHub before a coding agent is
        dispatched (Google Jules and other cloud agents clone from an existing ref).

        When the branch is missing it is created from `base_branch` (falling back to
        the repository default branch).

        Returns a dictionary with:
          - branch:      the verified/created branch name
          - base_branch: the branch it was created from
          - verified:    True when GitHub confirmed (or created) the branch
          - created:     True when a new ref was pushed to GitHub
          - sha:         commit SHA the branch currently points at
          - simulated:   True when running against mocked GitHub credentials

        Raises GitHubAuthError / GitHubAPIError when the branch is missing and cannot
        be created, so callers can halt dispatch instead of failing silently.

        When the repository itself is not resolvable (404), GitHub gives us nothing to
        verify. `allow_unverifiable=True` downgrades that case to a warning result with
        verified=False (used for offline/mock repositories); the default strict mode
        raises instead.
        """
        full_repo = self._normalize_repo(repo)

        existing = self.get_branch(full_repo, branch)
        if existing:
            logger.info(f"GitHub branch verified before dispatch: {full_repo}#{branch}")
            return {
                "branch": branch,
                "base_branch": base_branch,
                "verified": True,
                "created": False,
                "sha": existing.get("sha"),
                "simulated": existing.get("simulated", False)
            }

        if not create_if_missing:
            raise GitHubAPIError(
                f"Branch '{branch}' does not exist in {full_repo} and create_if_missing is disabled."
            )

        if self._is_simulated():
            logger.info(f"[SIMULATION] Created simulated branch {full_repo}#{branch} from '{base_branch}'")
            return {
                "branch": branch,
                "base_branch": base_branch,
                "verified": True,
                "created": True,
                "sha": "simulated_sha",
                "simulated": True
            }

        try:
            base_sha = self._resolve_base_sha(full_repo, base_branch)
        except GitHubRepoNotFoundError as repo_err:
            if not allow_unverifiable:
                raise
            logger.warning(
                f"Branch preflight skipped: {repo_err} Cannot confirm '{branch}' before dispatch."
            )
            return {
                "branch": branch,
                "base_branch": base_branch,
                "verified": False,
                "created": False,
                "sha": None,
                "simulated": False,
                "skip_reason": str(repo_err)
            }

        if not base_sha:
            raise GitHubAPIError(
                f"Cannot create branch '{branch}' in {full_repo}: base branch '{base_branch}' "
                f"(or the repository default branch) could not be resolved."
            )

        headers = self._branch_headers()
        payload = {"ref": f"refs/heads/{branch}", "sha": base_sha}

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    f"{self.base_url}/repos/{full_repo}/git/refs",
                    json=payload,
                    headers=headers
                )
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error creating branch '{branch}' in {full_repo}: {exc}")

        if resp.status_code == 201:
            data = resp.json()
            created_sha = (data.get("object") or {}).get("sha") or base_sha
            logger.info(f"Created GitHub branch {full_repo}#{branch} from '{base_branch}' ({created_sha[:8]})")
            return {
                "branch": branch,
                "base_branch": base_branch,
                "verified": True,
                "created": True,
                "sha": created_sha,
                "simulated": False
            }
        if resp.status_code == 422:
            # Ref may have been created concurrently by another worker
            race_winner = self.get_branch(full_repo, branch)
            if race_winner:
                logger.info(f"Branch {full_repo}#{branch} was created concurrently; reusing it.")
                return {
                    "branch": branch,
                    "base_branch": base_branch,
                    "verified": True,
                    "created": False,
                    "sha": race_winner.get("sha"),
                    "simulated": False
                }
            raise GitHubAPIError(
                f"GitHub rejected branch creation for {full_repo}#{branch} (422): {resp.text}"
            )
        if resp.status_code in (401, 403):
            raise GitHubAuthError(f"GitHub authentication error ({resp.status_code}): {resp.text}")
        raise GitHubAPIError(
            f"Failed to create branch '{branch}' in {full_repo} ({resp.status_code}): {resp.text}"
        )


github_service = GitHubService()
