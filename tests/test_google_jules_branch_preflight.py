"""
Tests for the GitHub branch preflight that guards Google Jules dispatch.

Covers:
  1. GitHubService.ensure_branch verifying an existing branch without creating refs.
  2. GitHubService.ensure_branch creating a missing branch from main (and falling back
     to the repository default branch).
  3. GitHubService.ensure_branch failing loudly when the base ref cannot be resolved,
     and downgrading to verified=False when allow_unverifiable=True.
  4. GoogleJulesOrchestrator consulting the preflight before creating a Jules session.
  5. GoogleJulesOrchestrator aborting dispatch (status="failed") when the preflight fails,
     or warning and proceeding in advisory mode.
"""

import json

import pytest

from backend.coding_agents.google_jules import (
    GoogleJulesOrchestrator,
    JulesBranchPreflightError
)
import backend.coding_agents.google_jules as jules_module
import services.github_service as github_module
from services.github_service import (
    GitHubService,
    GitHubAPIError,
    GitHubAuthError,
    GitHubRepoNotFoundError,
    github_service
)


class FakeResponse:
    """Minimal httpx.Response stand-in."""

    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text if text is not None else json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeHttpClient:
    """Minimal httpx.Client stand-in that routes requests and records calls."""

    def __init__(self, routes=None):
        # routes: list of (METHOD, url_suffix, FakeResponse)
        self.routes = routes or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def _request(self, method, url, body=None):
        self.calls.append((method, url, body))
        for route_method, url_suffix, response in self.routes:
            if route_method == method and url.endswith(url_suffix):
                return response
        return FakeResponse(404, {}, "Not Found")

    def get(self, url, headers=None):
        return self._request("GET", url)

    def post(self, url, json=None, headers=None):
        return self._request("POST", url, json)


def _install_fake_client(monkeypatch, fake_client, module=github_module):
    """Routes httpx.Client construction inside the target module to the fake client."""
    monkeypatch.setattr(module.httpx, "Client", lambda timeout=None: fake_client)
    return fake_client


def _live_service():
    return GitHubService(token="ghp_unit_test_token", simulation_mode=False)


BRANCH = "hephaestus/wh-101-task_1"
REPO = "org/repo"
COMMIT_SHA = "a" * 40


def test_ensure_branch_reuses_existing_branch_without_creating_ref(monkeypatch):
    """An existing branch is confirmed as-is; no ref creation call is issued."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(200, {
            "name": BRANCH,
            "protected": True,
            "commit": {"sha": COMMIT_SHA}
        }))
    ])
    _install_fake_client(monkeypatch, fake)

    result = _live_service().ensure_branch(f"https://github.com/{REPO}.git", BRANCH)

    assert result["branch"] == BRANCH
    assert result["created"] is False
    assert result["sha"] == COMMIT_SHA
    assert result["simulated"] is False
    assert not [call for call in fake.calls if call[0] == "POST"]


def test_ensure_branch_creates_missing_branch_from_main(monkeypatch):
    """A missing branch is created from main and the created ref payload is correct."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}/git/ref/heads/main", FakeResponse(200, {"object": {"sha": COMMIT_SHA}})),
        ("POST", f"/repos/{REPO}/git/refs", FakeResponse(201, {
            "ref": f"refs/heads/{BRANCH}",
            "object": {"sha": COMMIT_SHA}
        }))
    ])
    _install_fake_client(monkeypatch, fake)

    result = _live_service().ensure_branch(REPO, BRANCH, base_branch="main")

    assert result["branch"] == BRANCH
    assert result["base_branch"] == "main"
    assert result["created"] is True
    assert result["sha"] == COMMIT_SHA
    assert result["simulated"] is False

    post_calls = [call for call in fake.calls if call[0] == "POST"]
    assert len(post_calls) == 1
    assert post_calls[0][2] == {"ref": f"refs/heads/{BRANCH}", "sha": COMMIT_SHA}


def test_ensure_branch_falls_back_to_repository_default_branch(monkeypatch):
    """When 'main' does not exist, creation branches from the repository default branch."""
    develop_sha = "c" * 40
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}/git/ref/heads/main", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}", FakeResponse(200, {"default_branch": "develop"})),
        ("GET", f"/repos/{REPO}/git/ref/heads/develop", FakeResponse(200, {"object": {"sha": develop_sha}})),
        ("POST", f"/repos/{REPO}/git/refs", FakeResponse(201, {"object": {"sha": develop_sha}}))
    ])
    _install_fake_client(monkeypatch, fake)

    result = _live_service().ensure_branch(REPO, BRANCH, base_branch="main")

    assert result["created"] is True
    assert result["sha"] == develop_sha
    post_calls = [call for call in fake.calls if call[0] == "POST"]
    assert post_calls[0][2]["sha"] == develop_sha


def test_ensure_branch_raises_when_base_ref_cannot_be_resolved(monkeypatch):
    """An unresolved base ref must raise instead of dispatching against a missing branch."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}/git/ref/heads/main", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}", FakeResponse(200, {"default_branch": None}))
    ])
    _install_fake_client(monkeypatch, fake)

    with pytest.raises(GitHubAPIError) as exc_info:
        _live_service().ensure_branch(REPO, BRANCH)

    assert "could not be resolved" in str(exc_info.value)
    assert not [call for call in fake.calls if call[0] == "POST"]


def test_ensure_branch_raises_when_repo_not_found_by_default(monkeypatch):
    """Strict mode raises when the repository itself is not resolvable."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}/git/ref/heads/main", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}", FakeResponse(404, {"message": "Not Found"}, "Not Found"))
    ])
    _install_fake_client(monkeypatch, fake)

    with pytest.raises(GitHubRepoNotFoundError):
        _live_service().ensure_branch(REPO, BRANCH)


def test_ensure_branch_reports_unverified_when_allowed(monkeypatch):
    """allow_unverifiable downgrades an unreachable repository to verified=False."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}/git/ref/heads/main", FakeResponse(404, {}, "Not Found")),
        ("GET", f"/repos/{REPO}", FakeResponse(404, {"message": "Not Found"}, "Not Found"))
    ])
    _install_fake_client(monkeypatch, fake)

    result = _live_service().ensure_branch(REPO, BRANCH, allow_unverifiable=True)

    assert result["verified"] is False
    assert result["created"] is False
    assert result["branch"] == BRANCH
    assert REPO in result["skip_reason"]


def test_ensure_branch_raises_when_creation_disabled(monkeypatch):
    """create_if_missing=False turns a missing branch into an explicit error."""
    fake = FakeHttpClient([
        ("GET", f"/repos/{REPO}/branches/{BRANCH}", FakeResponse(404, {}, "Not Found"))
    ])
    _install_fake_client(monkeypatch, fake)

    with pytest.raises(GitHubAPIError) as exc_info:
        _live_service().ensure_branch(REPO, BRANCH, create_if_missing=False)

    assert "does not exist" in str(exc_info.value)
    assert not [call for call in fake.calls if call[0] == "POST"]


def test_ensure_branch_requires_github_token():
    """Missing GITHUB_TOKEN fails fast rather than silently proceeding to Jules."""
    service = GitHubService(token="", simulation_mode=False)

    with pytest.raises(GitHubAuthError) as exc_info:
        service.ensure_branch(REPO, BRANCH)

    assert "GITHUB_TOKEN" in str(exc_info.value)


def test_ensure_branch_is_simulated_with_mock_token():
    """Mocked GitHub credentials resolve locally without issuing any HTTP calls."""
    service = GitHubService(token="mock_token", simulation_mode=False)

    result = service.ensure_branch(REPO, BRANCH)

    assert result["branch"] == BRANCH
    assert result["simulated"] is True
    assert result["sha"] == "simulated_sha"


@pytest.mark.parametrize("repo_input", [
    "org/repo",
    "https://github.com/org/repo",
    "https://github.com/org/repo.git",
    "git@github.com:org/repo.git"
])
def test_normalize_repo_variants(repo_input):
    """Repository coordinates are normalized to 'owner/name' for API calls."""
    assert GitHubService._normalize_repo(repo_input) == REPO


def _jules_agent_and_env():
    agent = GoogleJulesOrchestrator(api_key="live_jules_test_key")
    container_env = agent.initiate_container(
        project_key="WH",
        branch_name=BRANCH,
        repo_url=f"https://github.com/{REPO}"
    )
    return agent, container_env


def test_google_jules_dispatch_consults_branch_preflight_before_session(monkeypatch):
    """The target branch is verified/created before the Jules session request is sent."""
    recorded = {}

    def fake_ensure_branch(repo, branch, base_branch="main", **kwargs):
        recorded["repo"] = repo
        recorded["branch"] = branch
        recorded["base_branch"] = base_branch
        recorded["create_if_missing"] = kwargs.get("create_if_missing")
        recorded["allow_unverifiable"] = kwargs.get("allow_unverifiable")
        return {
            "branch": branch,
            "base_branch": base_branch,
            "verified": True,
            "created": True,
            "sha": "f" * 40,
            "simulated": False
        }

    monkeypatch.setattr(github_service, "ensure_branch", fake_ensure_branch)

    session_client = FakeHttpClient([
        ("POST", "/v1alpha/sessions", FakeResponse(201, {"name": "sessions/jules_123"}))
    ])
    _install_fake_client(monkeypatch, session_client, module=jules_module)

    agent, container_env = _jules_agent_and_env()
    result = agent.execute_in_container(
        prompt="Implement rate limiter for the payments endpoint.",
        container_env=container_env,
        project_config={"key": "WH", "branch_name": BRANCH, "repo_url": f"https://github.com/{REPO}"}
    )

    assert recorded == {
        "repo": REPO,
        "branch": BRANCH,
        "base_branch": "main",
        "create_if_missing": True,
        "allow_unverifiable": True
    }
    assert result.status == "completed"
    assert result.session_id == "sessions/jules_123"

    # Preflight must happen before the session POST
    session_posts = [call for call in session_client.calls if call[0] == "POST"]
    assert len(session_posts) == 1
    assert session_posts[0][2]["sourceContext"]["githubRepoContext"]["startingBranch"] == BRANCH


def test_google_jules_dispatch_aborts_when_branch_preflight_fails(monkeypatch):
    """A branch that cannot be verified/created blocks dispatch with status='failed'."""

    def failing_ensure_branch(repo, branch, base_branch="main", **kwargs):
        raise GitHubAPIError(
            "GitHub authentication token (GITHUB_TOKEN) is missing or empty. "
            "Cannot proceed with remote GitHub branch verification."
        )

    monkeypatch.setattr(github_service, "ensure_branch", failing_ensure_branch)

    agent, container_env = _jules_agent_and_env()
    project_config = {"key": "WH", "branch_name": BRANCH, "repo_url": f"https://github.com/{REPO}"}

    with pytest.raises(JulesBranchPreflightError):
        agent._dispatch_jules_api(
            "Implement rate limiter for the payments endpoint.",
            container_env,
            project_config
        )

    result = agent.execute_in_container(
        prompt="Implement rate limiter for the payments endpoint.",
        container_env=container_env,
        project_config=project_config
    )

    assert result.status == "failed"
    assert "preflight" in result.full_log.lower()
    assert "GITHUB_TOKEN" in result.what_was_wrong


def test_google_jules_advisory_mode_proceeds_when_preflight_fails(monkeypatch):
    """In advisory mode a failed preflight logs a warning instead of blocking dispatch."""

    def failing_ensure_branch(repo, branch, base_branch="main", **kwargs):
        raise GitHubAPIError("GitHub API unavailable during branch preflight.")

    monkeypatch.setattr(github_service, "ensure_branch", failing_ensure_branch)
    monkeypatch.setattr("backend.config.JULES_BRANCH_PREFLIGHT_MODE", "advisory", raising=False)

    session_client = FakeHttpClient([
        ("POST", "/v1alpha/sessions", FakeResponse(201, {"name": "sessions/jules_advisory"}))
    ])
    _install_fake_client(monkeypatch, session_client, module=jules_module)

    agent, container_env = _jules_agent_and_env()
    result = agent.execute_in_container(
        prompt="Implement rate limiter for the payments endpoint.",
        container_env=container_env,
        project_config={"key": "WH", "branch_name": BRANCH, "repo_url": f"https://github.com/{REPO}"}
    )

    assert result.status == "completed"
    assert result.session_id == "sessions/jules_advisory"
