# Bitbucket MCP Server Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** MCP server for Bitbucket Cloud enabling full PR lifecycle management (create, review, comment, update, check pipelines, merge).

**Architecture:** Standalone Python + FastMCP server mirroring the jira-confluence project structure. HTTP client wraps Bitbucket Cloud REST API 2.0 with Basic Auth. 14 tools exposed via `@mcp.tool()` decorators.

**Tech Stack:** Python 3.10+, FastMCP (`mcp>=1.20.0`), `requests`, `python-dotenv`, `pytest` + `responses` for testing.

**Reference project:** `jira-confluence (sibling MCP server)`

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `bitbucket_mcp/__init__.py`
- Create: `bitbucket_mcp/__main__.py`
- Create: `.env.example`

**Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "bitbucket-mcp"
version = "0.1.0"
description = "MCP server for Bitbucket Cloud REST API integration"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.20.0",
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
]

[project.scripts]
bitbucket-mcp = "bitbucket_mcp.server:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "responses>=0.23.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["bitbucket_mcp*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
```

**Step 2: Create bitbucket_mcp/__init__.py**

```python
"""
MCP Server for Bitbucket Cloud REST API integration.
"""

__version__ = "0.1.0"
```

**Step 3: Create bitbucket_mcp/__main__.py**

```python
"""Entry point for running the MCP server as a module."""

from bitbucket_mcp.server import main

if __name__ == "__main__":
    main()
```

**Step 4: Create .env.example**

```
BITBUCKET_EMAIL=your-email@example.com
BITBUCKET_API_TOKEN=your-api-token
BITBUCKET_WORKSPACE=your-workspace
```

**Step 5: Install dev dependencies**

Run: `cd /path/to/bitbucket-mcp && uv sync --dev`

**Step 6: Commit**

```bash
git add pyproject.toml bitbucket_mcp/__init__.py bitbucket_mcp/__main__.py .env.example
git commit -m "feat: scaffold bitbucket-mcp project structure"
```

---

### Task 2: Error Handling Module

**Files:**
- Create: `bitbucket_mcp/errors.py`
- Create: `tests/test_errors.py`

**Step 1: Write tests for error classes**

```python
"""Tests for bitbucket_mcp.errors module."""

import pytest
import requests
from unittest.mock import MagicMock

from bitbucket_mcp.errors import (
    BitbucketError,
    AuthenticationError,
    PermissionError as BbPermissionError,
    NotFoundError,
    ConflictError,
    RateLimitError,
    handle_api_error,
)


class TestBitbucketError:
    def test_to_dict_basic(self):
        err = BitbucketError("something broke")
        assert err.to_dict() == {"error": "something broke"}

    def test_to_dict_with_status_and_details(self):
        err = BitbucketError("fail", status_code=500, details="server error")
        result = err.to_dict()
        assert result["error"] == "fail"
        assert result["status_code"] == 500
        assert result["details"] == "server error"


class TestHandleApiError:
    def _mock_response(self, status_code, json_body=None, text=""):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.text = text
        if json_body is not None:
            resp.json.return_value = json_body
        else:
            resp.json.side_effect = ValueError("No JSON")
        return resp

    def test_401_raises_authentication_error(self):
        resp = self._mock_response(401, {"error": {"message": "Unauthorized"}})
        with pytest.raises(AuthenticationError):
            handle_api_error(resp)

    def test_403_raises_permission_error(self):
        resp = self._mock_response(403, {"error": {"message": "Forbidden"}})
        with pytest.raises(BbPermissionError):
            handle_api_error(resp)

    def test_404_raises_not_found_error(self):
        resp = self._mock_response(404, {"error": {"message": "Not found"}})
        with pytest.raises(NotFoundError):
            handle_api_error(resp)

    def test_409_raises_conflict_error(self):
        resp = self._mock_response(409, {"error": {"message": "Merge conflict"}})
        with pytest.raises(ConflictError):
            handle_api_error(resp)

    def test_429_raises_rate_limit_error(self):
        resp = self._mock_response(429, {"error": {"message": "Rate limited"}})
        with pytest.raises(RateLimitError):
            handle_api_error(resp)

    def test_non_json_response(self):
        resp = self._mock_response(500, json_body=None, text="Internal Server Error")
        with pytest.raises(BitbucketError, match="Internal Server Error"):
            handle_api_error(resp)
```

**Step 2: Run tests to verify they fail**

Run: `cd /path/to/bitbucket-mcp && uv run pytest tests/test_errors.py -v`
Expected: FAIL (module not found)

**Step 3: Implement errors.py**

```python
"""Error handling for Bitbucket Cloud API interactions."""

import requests
from typing import Optional


class BitbucketError(Exception):
    """Base exception for Bitbucket operations."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)

    def to_dict(self) -> dict:
        result = {"error": self.message}
        if self.status_code:
            result["status_code"] = self.status_code
        if self.details:
            result["details"] = self.details
        return result


class AuthenticationError(BitbucketError):
    pass


class PermissionError(BitbucketError):
    pass


class NotFoundError(BitbucketError):
    pass


class ConflictError(BitbucketError):
    pass


class BadRequestError(BitbucketError):
    pass


class RateLimitError(BitbucketError):
    pass


class ServerError(BitbucketError):
    pass


def handle_api_error(response: requests.Response) -> None:
    try:
        error_data = response.json()
        error_message = error_data.get("error", {}).get("message", response.text)
        details = str(error_data)
    except Exception:
        error_message = response.text or f"HTTP {response.status_code}"
        details = None

    status_code = response.status_code

    if status_code == 400:
        raise BadRequestError(f"Bad request: {error_message}", status_code=status_code, details=details)
    elif status_code == 401:
        raise AuthenticationError("Authentication failed. Check your email and app password.", status_code=status_code, details=details)
    elif status_code == 403:
        raise PermissionError("Permission denied.", status_code=status_code, details=details)
    elif status_code == 404:
        raise NotFoundError(f"Resource not found: {error_message}", status_code=status_code, details=details)
    elif status_code == 409:
        raise ConflictError(f"Conflict: {error_message}", status_code=status_code, details=details)
    elif status_code == 429:
        raise RateLimitError("Rate limit exceeded. Try again later.", status_code=status_code, details=details)
    elif status_code >= 500:
        raise ServerError(f"Server error: {error_message}", status_code=status_code, details=details)
    else:
        raise BitbucketError(f"Request failed: {error_message}", status_code=status_code, details=details)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_errors.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add bitbucket_mcp/errors.py tests/test_errors.py
git commit -m "feat: add error handling module with tests"
```

---

### Task 3: HTTP Client — Core + PR Methods

**Files:**
- Create: `bitbucket_mcp/client.py`
- Create: `tests/test_client.py`

**Step 1: Write tests for client init and PR methods**

```python
"""Tests for bitbucket_mcp.client module."""

import pytest
import responses
from responses import matchers

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.errors import AuthenticationError, NotFoundError, ConflictError

BASE = "https://api.bitbucket.org/2.0"


@pytest.fixture
def client():
    return BitbucketClient(
        email="test@example.com",
        api_token="test-token",
        workspace="testws",
    )


class TestClientInit:
    def test_creates_session_with_basic_auth(self, client):
        assert client.session.auth is not None
        assert client.workspace == "testws"
        assert client.base_url == BASE


class TestListPullRequests:
    @responses.activate
    def test_list_open_prs(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "id": 1,
                        "title": "Test PR",
                        "state": "OPEN",
                        "author": {"display_name": "Alice"},
                        "source": {"branch": {"name": "feature/x"}},
                        "destination": {"branch": {"name": "main"}},
                        "created_on": "2025-01-01T00:00:00+00:00",
                        "updated_on": "2025-01-02T00:00:00+00:00",
                        "comment_count": 3,
                    }
                ],
            },
        )
        result = client.list_pull_requests("myrepo")
        assert len(result["values"]) == 1
        assert result["values"][0]["title"] == "Test PR"

    @responses.activate
    def test_list_prs_with_state_filter(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={"pagelen": 10, "size": 0, "values": []},
        )
        client.list_pull_requests("myrepo", state="MERGED")
        assert "state=MERGED" in responses.calls[0].request.url


class TestGetPullRequest:
    @responses.activate
    def test_get_pr_by_id(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42",
            json={"id": 42, "title": "My PR", "state": "OPEN"},
        )
        result = client.get_pull_request("myrepo", 42)
        assert result["id"] == 42

    @responses.activate
    def test_get_pr_not_found(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/999",
            json={"error": {"message": "Not found"}},
            status=404,
        )
        with pytest.raises(NotFoundError):
            client.get_pull_request("myrepo", 999)


class TestCreatePullRequest:
    @responses.activate
    def test_create_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests",
            json={"id": 100, "title": "New PR", "state": "OPEN"},
            status=201,
        )
        result = client.create_pull_request(
            "myrepo",
            title="New PR",
            source_branch="feature/new",
            destination_branch="main",
            description="Some changes",
        )
        assert result["id"] == 100
        body = responses.calls[0].request.body
        assert "feature/new" in body


class TestMergePullRequest:
    @responses.activate
    def test_merge_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/merge",
            json={"id": 42, "state": "MERGED"},
        )
        result = client.merge_pull_request("myrepo", 42)
        assert result["state"] == "MERGED"

    @responses.activate
    def test_merge_conflict(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/merge",
            json={"error": {"message": "Merge conflict"}},
            status=409,
        )
        with pytest.raises(ConflictError):
            client.merge_pull_request("myrepo", 42)


class TestDeclinePullRequest:
    @responses.activate
    def test_decline_pr(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/decline",
            json={"id": 42, "state": "DECLINED"},
        )
        result = client.decline_pull_request("myrepo", 42)
        assert result["state"] == "DECLINED"


class TestUpdatePullRequest:
    @responses.activate
    def test_update_title_and_description(self, client):
        responses.add(
            responses.PUT,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42",
            json={"id": 42, "title": "Updated", "description": "New desc"},
        )
        result = client.update_pull_request("myrepo", 42, title="Updated", description="New desc")
        assert result["title"] == "Updated"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v`
Expected: FAIL (module not found)

**Step 3: Implement client.py — core + PR methods**

```python
"""Bitbucket Cloud REST API client."""

import requests
from typing import Any, Dict, List, Optional
from requests.auth import HTTPBasicAuth

from bitbucket_mcp.errors import BitbucketError, handle_api_error

BASE_URL = "https://api.bitbucket.org/2.0"


class BitbucketClient:

    def __init__(self, email: str, api_token: str, workspace: str):
        self.base_url = BASE_URL
        self.workspace = workspace
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(email, api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _repo_url(self, repo_slug: str, workspace: Optional[str] = None) -> str:
        ws = workspace or self.workspace
        return f"{self.base_url}/repositories/{ws}/{repo_slug}"

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        accept: Optional[str] = None,
        timeout: int = 30,
    ) -> Any:
        headers = {}
        if accept:
            headers["Accept"] = accept

        try:
            response = self.session.request(
                method=method, url=url, params=params, json=json,
                headers=headers, timeout=timeout,
            )
            if not response.ok:
                handle_api_error(response)

            if response.status_code == 204 or not response.content:
                return {}

            if accept and "json" not in accept:
                return response.text

            return response.json()
        except requests.exceptions.Timeout:
            raise BitbucketError(f"Request timeout after {timeout}s")
        except requests.exceptions.ConnectionError:
            raise BitbucketError(f"Failed to connect to {self.base_url}")
        except BitbucketError:
            raise
        except requests.exceptions.RequestException as e:
            raise BitbucketError(f"Request failed: {str(e)}")

    # ===== PULL REQUESTS =====

    def list_pull_requests(
        self, repo_slug: str, state: str = "OPEN",
        page: int = 1, pagelen: int = 25, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests"
        params = {"state": state, "page": page, "pagelen": pagelen}
        return self._request("GET", url, params=params)

    def get_pull_request(
        self, repo_slug: str, pr_id: int, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}"
        return self._request("GET", url)

    def create_pull_request(
        self, repo_slug: str, title: str, source_branch: str,
        destination_branch: str = "main", description: str = "",
        reviewers: Optional[List[str]] = None, close_source_branch: bool = True,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests"
        payload: Dict[str, Any] = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": destination_branch}},
            "description": description,
            "close_source_branch": close_source_branch,
        }
        if reviewers:
            payload["reviewers"] = [{"uuid": uuid} for uuid in reviewers]
        return self._request("POST", url, json=payload)

    def update_pull_request(
        self, repo_slug: str, pr_id: int, title: Optional[str] = None,
        description: Optional[str] = None, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}"
        payload: Dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        return self._request("PUT", url, json=payload)

    def merge_pull_request(
        self, repo_slug: str, pr_id: int, merge_strategy: str = "merge_commit",
        message: Optional[str] = None, close_source_branch: bool = True,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/merge"
        payload: Dict[str, Any] = {
            "type": "pullrequest",
            "merge_strategy": merge_strategy,
            "close_source_branch": close_source_branch,
        }
        if message:
            payload["message"] = message
        return self._request("POST", url, json=payload)

    def decline_pull_request(
        self, repo_slug: str, pr_id: int, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/decline"
        return self._request("POST", url)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add bitbucket_mcp/client.py tests/test_client.py
git commit -m "feat: add HTTP client with PR methods and tests"
```

---

### Task 4: Client — Comments, Review, Diff Methods

**Files:**
- Modify: `bitbucket_mcp/client.py`
- Modify: `tests/test_client.py`

**Step 1: Add tests for comment/review/diff methods to tests/test_client.py**

Append these test classes:

```python
class TestListPrComments:
    @responses.activate
    def test_list_comments(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "id": 1,
                        "content": {"raw": "Looks good!"},
                        "user": {"display_name": "Alice"},
                        "created_on": "2025-01-01T00:00:00+00:00",
                    }
                ],
            },
        )
        result = client.list_pr_comments("myrepo", 42)
        assert len(result["values"]) == 1


class TestAddPrComment:
    @responses.activate
    def test_add_general_comment(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={"id": 10, "content": {"raw": "Nice work!"}},
            status=201,
        )
        result = client.add_pr_comment("myrepo", 42, "Nice work!")
        assert result["id"] == 10


class TestAddPrInlineComment:
    @responses.activate
    def test_add_inline_comment(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/comments",
            json={"id": 11, "content": {"raw": "Fix this"}, "inline": {"path": "src/main.py", "to": 10}},
            status=201,
        )
        result = client.add_pr_inline_comment("myrepo", 42, "Fix this", "src/main.py", to_line=10)
        assert result["inline"]["path"] == "src/main.py"


class TestApprovePullRequest:
    @responses.activate
    def test_approve(self, client):
        responses.add(
            responses.POST,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/approve",
            json={"approved": True, "user": {"display_name": "Me"}},
        )
        result = client.approve_pull_request("myrepo", 42)
        assert result["approved"] is True


class TestGetPrDiff:
    @responses.activate
    def test_get_diff(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pullrequests/42/diff",
            body="diff --git a/file.py b/file.py\n+new line\n",
            content_type="text/plain",
        )
        result = client.get_pr_diff("myrepo", 42)
        assert "diff --git" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v -k "Comment or Approve or Diff"`
Expected: FAIL (methods not found)

**Step 3: Add comment/review/diff methods to client.py**

Append to `BitbucketClient` class:

```python
    # ===== COMMENTS =====

    def list_pr_comments(
        self, repo_slug: str, pr_id: int, page: int = 1,
        pagelen: int = 50, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/comments"
        params = {"page": page, "pagelen": pagelen}
        return self._request("GET", url, params=params)

    def add_pr_comment(
        self, repo_slug: str, pr_id: int, text: str,
        parent_id: Optional[int] = None, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/comments"
        payload: Dict[str, Any] = {"content": {"raw": text}}
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", url, json=payload)

    def add_pr_inline_comment(
        self, repo_slug: str, pr_id: int, text: str, file_path: str,
        to_line: Optional[int] = None, from_line: Optional[int] = None,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/comments"
        inline: Dict[str, Any] = {"path": file_path}
        if to_line is not None:
            inline["to"] = to_line
        if from_line is not None:
            inline["from"] = from_line
        payload: Dict[str, Any] = {"content": {"raw": text}, "inline": inline}
        return self._request("POST", url, json=payload)

    # ===== REVIEW =====

    def approve_pull_request(
        self, repo_slug: str, pr_id: int, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/approve"
        return self._request("POST", url)

    def get_pr_diff(
        self, repo_slug: str, pr_id: int, workspace: Optional[str] = None,
    ) -> str:
        url = f"{self._repo_url(repo_slug, workspace)}/pullrequests/{pr_id}/diff"
        return self._request("GET", url, accept="text/plain")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add bitbucket_mcp/client.py tests/test_client.py
git commit -m "feat: add comment, review, and diff methods to client"
```

---

### Task 5: Client — Pipeline Methods

**Files:**
- Modify: `bitbucket_mcp/client.py`
- Modify: `tests/test_client.py`

**Step 1: Add pipeline tests to tests/test_client.py**

Append:

```python
class TestListPipelines:
    @responses.activate
    def test_list_pipelines(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/",
            json={
                "pagelen": 10,
                "size": 1,
                "values": [
                    {
                        "uuid": "{pipe-uuid}",
                        "build_number": 42,
                        "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
                        "target": {"ref_name": "main", "commit": {"hash": "abc123"}},
                        "created_on": "2025-01-01T00:00:00+00:00",
                    }
                ],
            },
        )
        result = client.list_pipelines("myrepo")
        assert len(result["values"]) == 1
        assert result["values"][0]["build_number"] == 42


class TestGetPipeline:
    @responses.activate
    def test_get_pipeline(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/%7Bpipe-uuid%7D",
            json={
                "uuid": "{pipe-uuid}",
                "build_number": 42,
                "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}},
            },
        )
        result = client.get_pipeline("myrepo", "{pipe-uuid}")
        assert result["build_number"] == 42


class TestGetPipelineStepLog:
    @responses.activate
    def test_get_step_log(self, client):
        responses.add(
            responses.GET,
            f"{BASE}/repositories/testws/myrepo/pipelines/%7Bpipe-uuid%7D/steps/%7Bstep-uuid%7D/log",
            body="Step 1: Installing dependencies...\nStep 2: Running tests...\nDone.",
            content_type="application/octet-stream",
        )
        result = client.get_pipeline_step_log("myrepo", "{pipe-uuid}", "{step-uuid}")
        assert "Installing dependencies" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py -v -k "Pipeline"`
Expected: FAIL

**Step 3: Add pipeline methods to client.py**

Append to `BitbucketClient` class:

```python
    # ===== PIPELINES =====

    def list_pipelines(
        self, repo_slug: str, page: int = 1, pagelen: int = 25,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pipelines/"
        params = {"page": page, "pagelen": pagelen, "sort": "-created_on"}
        return self._request("GET", url, params=params)

    def get_pipeline(
        self, repo_slug: str, pipeline_uuid: str, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pipelines/{pipeline_uuid}"
        return self._request("GET", url)

    def get_pipeline_steps(
        self, repo_slug: str, pipeline_uuid: str, workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, workspace)}/pipelines/{pipeline_uuid}/steps/"
        return self._request("GET", url)

    def get_pipeline_step_log(
        self, repo_slug: str, pipeline_uuid: str, step_uuid: str,
        workspace: Optional[str] = None,
    ) -> str:
        url = f"{self._repo_url(repo_slug, workspace)}/pipelines/{pipeline_uuid}/steps/{step_uuid}/log"
        return self._request("GET", url, accept="application/octet-stream")
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_client.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add bitbucket_mcp/client.py tests/test_client.py
git commit -m "feat: add pipeline methods to client"
```

---

### Task 6: Server — All MCP Tools

**Files:**
- Create: `bitbucket_mcp/server.py`

This is the largest task. It creates the FastMCP server with all 14 tools. Each tool follows the same pattern: `get_client()`, call client method, format response, catch errors.

**Step 1: Create server.py**

```python
"""MCP Server for Bitbucket Cloud integration."""

import os
import sys
from typing import Optional
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.errors import BitbucketError

load_dotenv()

mcp = FastMCP("Bitbucket MCP Server")

_client: Optional[BitbucketClient] = None


def get_client() -> BitbucketClient:
    global _client
    if _client is None:
        email = os.getenv("BITBUCKET_EMAIL")
        api_token = os.getenv("BITBUCKET_API_TOKEN")
        workspace = os.getenv("BITBUCKET_WORKSPACE", "")

        if not all([email, api_token]):
            missing = []
            if not email:
                missing.append("BITBUCKET_EMAIL")
            if not api_token:
                missing.append("BITBUCKET_API_TOKEN")
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        _client = BitbucketClient(email, api_token, workspace)
    return _client


# ===== PULL REQUEST TOOLS =====

@mcp.tool()
def bb_list_pull_requests(
    repo_slug: str, state: str = "OPEN", page: int = 1,
    pagelen: int = 25, workspace: str = "",
) -> dict:
    """
    List pull requests for a Bitbucket repository.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        state: PR state filter — OPEN, MERGED, DECLINED, SUPERSEDED (default: OPEN)
        page: Page number for pagination (default: 1)
        pagelen: Results per page, max 50 (default: 25)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        List of pull requests with id, title, state, author, branches, dates

    Example:
        bb_list_pull_requests("my-repo")
        bb_list_pull_requests("my-repo", state="MERGED", pagelen=10)
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.list_pull_requests(repo_slug, state=state, page=page, pagelen=pagelen, workspace=ws)

        prs = []
        for pr in result.get("values", []):
            prs.append({
                "id": pr.get("id"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "author": pr.get("author", {}).get("display_name", "Unknown"),
                "source_branch": pr.get("source", {}).get("branch", {}).get("name"),
                "destination_branch": pr.get("destination", {}).get("branch", {}).get("name"),
                "created_on": pr.get("created_on"),
                "updated_on": pr.get("updated_on"),
                "comment_count": pr.get("comment_count", 0),
            })

        return {"count": len(prs), "total": result.get("size", len(prs)), "page": page, "pull_requests": prs}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pull_request(repo_slug: str, pr_id: int, workspace: str = "") -> dict:
    """
    Get detailed information about a pull request including reviewers and approvals.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID (e.g., 302)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Full PR details: title, description, state, author, branches, reviewers,
        participants with approval status, comment/task counts, links

    Example:
        bb_get_pull_request("my-repo", 302)
    """
    try:
        client = get_client()
        ws = workspace or None
        pr = client.get_pull_request(repo_slug, pr_id, workspace=ws)

        participants = []
        for p in pr.get("participants", []):
            participants.append({
                "user": p.get("user", {}).get("display_name", "Unknown"),
                "role": p.get("role"),
                "approved": p.get("approved", False),
                "state": p.get("state"),
            })

        return {
            "id": pr.get("id"),
            "title": pr.get("title"),
            "description": pr.get("description", ""),
            "state": pr.get("state"),
            "author": pr.get("author", {}).get("display_name", "Unknown"),
            "source_branch": pr.get("source", {}).get("branch", {}).get("name"),
            "destination_branch": pr.get("destination", {}).get("branch", {}).get("name"),
            "created_on": pr.get("created_on"),
            "updated_on": pr.get("updated_on"),
            "comment_count": pr.get("comment_count", 0),
            "task_count": pr.get("task_count", 0),
            "participants": participants,
            "link": pr.get("links", {}).get("html", {}).get("href", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_create_pull_request(
    repo_slug: str, title: str, source_branch: str,
    destination_branch: str = "main", description: str = "",
    reviewers: Optional[list[str]] = None, close_source_branch: bool = True,
    workspace: str = "",
) -> dict:
    """
    Create a new pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        title: PR title
        source_branch: Source branch name (e.g., "feature/my-feature")
        destination_branch: Target branch name (default: "main")
        description: PR description in Markdown
        reviewers: Optional list of reviewer UUIDs (e.g., ["{uuid-1}", "{uuid-2}"])
        close_source_branch: Delete source branch after merge (default: true)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Created PR data with id, title, state, and link

    Example:
        bb_create_pull_request("my-repo", "Add login feature", "feature/login")
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.create_pull_request(
            repo_slug, title=title, source_branch=source_branch,
            destination_branch=destination_branch, description=description,
            reviewers=reviewers, close_source_branch=close_source_branch,
            workspace=ws,
        )
        return {
            "success": True,
            "id": result.get("id"),
            "title": result.get("title"),
            "state": result.get("state"),
            "link": result.get("links", {}).get("html", {}).get("href", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_update_pull_request(
    repo_slug: str, pr_id: int, title: Optional[str] = None,
    description: Optional[str] = None, workspace: str = "",
) -> dict:
    """
    Update a pull request's title and/or description.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        title: New title (optional, only updates if provided)
        description: New description in Markdown (optional, only updates if provided)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Updated PR data

    Example:
        bb_update_pull_request("my-repo", 302, description="## Updated description")
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.update_pull_request(repo_slug, pr_id, title=title, description=description, workspace=ws)
        return {
            "success": True,
            "id": result.get("id"),
            "title": result.get("title"),
            "state": result.get("state"),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_merge_pull_request(
    repo_slug: str, pr_id: int, merge_strategy: str = "merge_commit",
    message: str = "", close_source_branch: bool = True, workspace: str = "",
) -> dict:
    """
    Merge a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        merge_strategy: Merge strategy — merge_commit, squash, or fast_forward (default: merge_commit)
        message: Optional merge commit message
        close_source_branch: Delete source branch after merge (default: true)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Merged PR data with state=MERGED

    Example:
        bb_merge_pull_request("my-repo", 302, merge_strategy="squash")
    """
    try:
        client = get_client()
        ws = workspace or None
        msg = message or None
        result = client.merge_pull_request(
            repo_slug, pr_id, merge_strategy=merge_strategy,
            message=msg, close_source_branch=close_source_branch, workspace=ws,
        )
        return {
            "success": True,
            "id": result.get("id"),
            "state": result.get("state"),
            "merge_commit": result.get("merge_commit", {}).get("hash", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_decline_pull_request(repo_slug: str, pr_id: int, workspace: str = "") -> dict:
    """
    Decline (close without merging) a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Declined PR data with state=DECLINED

    Example:
        bb_decline_pull_request("my-repo", 302)
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.decline_pull_request(repo_slug, pr_id, workspace=ws)
        return {"success": True, "id": result.get("id"), "state": result.get("state")}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== COMMENT TOOLS =====

@mcp.tool()
def bb_list_pr_comments(
    repo_slug: str, pr_id: int, page: int = 1,
    pagelen: int = 50, workspace: str = "",
) -> dict:
    """
    List comments on a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        page: Page number (default: 1)
        pagelen: Results per page (default: 50)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        List of comments with author, text, and inline location (if any)

    Example:
        bb_list_pr_comments("my-repo", 302)
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.list_pr_comments(repo_slug, pr_id, page=page, pagelen=pagelen, workspace=ws)

        comments = []
        for c in result.get("values", []):
            comment = {
                "id": c.get("id"),
                "author": c.get("user", {}).get("display_name", "Unknown"),
                "text": c.get("content", {}).get("raw", ""),
                "created_on": c.get("created_on"),
            }
            inline = c.get("inline")
            if inline:
                comment["inline"] = {
                    "path": inline.get("path"),
                    "line": inline.get("to") or inline.get("from"),
                }
            parent = c.get("parent")
            if parent:
                comment["parent_id"] = parent.get("id")
            comments.append(comment)

        return {"count": len(comments), "total": result.get("size", len(comments)), "comments": comments}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_add_pr_comment(
    repo_slug: str, pr_id: int, text: str,
    parent_id: int = 0, workspace: str = "",
) -> dict:
    """
    Add a general comment to a pull request, or reply to an existing comment.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        text: Comment text in Markdown
        parent_id: ID of comment to reply to (optional, 0 = top-level comment)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Created comment data

    Example:
        bb_add_pr_comment("my-repo", 302, "Looks good overall!")
        bb_add_pr_comment("my-repo", 302, "Fixed, thanks!", parent_id=42)
    """
    try:
        client = get_client()
        ws = workspace or None
        pid = parent_id if parent_id else None
        result = client.add_pr_comment(repo_slug, pr_id, text, parent_id=pid, workspace=ws)
        return {
            "success": True,
            "id": result.get("id"),
            "author": result.get("user", {}).get("display_name", "Unknown"),
            "text": result.get("content", {}).get("raw", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_add_pr_inline_comment(
    repo_slug: str, pr_id: int, text: str, file_path: str,
    to_line: int = 0, from_line: int = 0, workspace: str = "",
) -> dict:
    """
    Add an inline comment on a specific file/line in a pull request diff.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        text: Comment text in Markdown
        file_path: File path relative to repo root (e.g., "src/main.py")
        to_line: Line number in the NEW version of the file (for added/unchanged lines)
        from_line: Line number in the OLD version (for deleted lines). If both to_line
                   and from_line are provided, to_line is ignored by Bitbucket.
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Created inline comment data

    Example:
        bb_add_pr_inline_comment("my-repo", 302, "Use a constant here", "src/main.py", to_line=42)
    """
    try:
        client = get_client()
        ws = workspace or None
        to_l = to_line if to_line else None
        from_l = from_line if from_line else None
        result = client.add_pr_inline_comment(
            repo_slug, pr_id, text, file_path,
            to_line=to_l, from_line=from_l, workspace=ws,
        )
        return {
            "success": True,
            "id": result.get("id"),
            "file": file_path,
            "line": to_line or from_line,
            "text": result.get("content", {}).get("raw", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== REVIEW TOOLS =====

@mcp.tool()
def bb_approve_pull_request(repo_slug: str, pr_id: int, workspace: str = "") -> dict:
    """
    Approve a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Approval confirmation with user info

    Example:
        bb_approve_pull_request("my-repo", 302)
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.approve_pull_request(repo_slug, pr_id, workspace=ws)
        return {
            "success": True,
            "approved": result.get("approved", True),
            "user": result.get("user", {}).get("display_name", "Unknown"),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pr_diff(repo_slug: str, pr_id: int, workspace: str = "") -> dict:
    """
    Get the raw unified diff of a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Raw diff text showing all file changes in unified diff format

    Example:
        bb_get_pr_diff("my-repo", 302)
    """
    try:
        client = get_client()
        ws = workspace or None
        diff_text = client.get_pr_diff(repo_slug, pr_id, workspace=ws)
        return {"diff": diff_text}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== PIPELINE TOOLS =====

@mcp.tool()
def bb_list_pipelines(
    repo_slug: str, page: int = 1, pagelen: int = 25, workspace: str = "",
) -> dict:
    """
    List recent pipelines for a repository, sorted by newest first.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        page: Page number (default: 1)
        pagelen: Results per page (default: 25)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        List of pipelines with build number, state, branch, trigger, and timing

    Example:
        bb_list_pipelines("my-repo")
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.list_pipelines(repo_slug, page=page, pagelen=pagelen, workspace=ws)

        pipelines = []
        for p in result.get("values", []):
            state = p.get("state", {})
            state_name = state.get("name", "UNKNOWN")
            result_name = state.get("result", {}).get("name", "") if state.get("result") else ""

            pipelines.append({
                "uuid": p.get("uuid"),
                "build_number": p.get("build_number"),
                "state": state_name,
                "result": result_name,
                "branch": p.get("target", {}).get("ref_name", ""),
                "commit": p.get("target", {}).get("commit", {}).get("hash", "")[:12],
                "trigger": p.get("trigger", {}).get("name", ""),
                "created_on": p.get("created_on"),
                "completed_on": p.get("completed_on"),
            })

        return {"count": len(pipelines), "total": result.get("size", len(pipelines)), "pipelines": pipelines}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pipeline(repo_slug: str, pipeline_uuid: str, workspace: str = "") -> dict:
    """
    Get details of a specific pipeline including its steps.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pipeline_uuid: Pipeline UUID (e.g., "{uuid-here}")
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Pipeline details with state, timing, and list of steps with their statuses

    Example:
        bb_get_pipeline("my-repo", "{some-pipeline-uuid}")
    """
    try:
        client = get_client()
        ws = workspace or None
        pipeline = client.get_pipeline(repo_slug, pipeline_uuid, workspace=ws)

        # Also fetch steps
        steps_result = client.get_pipeline_steps(repo_slug, pipeline_uuid, workspace=ws)
        steps = []
        for s in steps_result.get("values", []):
            step_state = s.get("state", {})
            steps.append({
                "uuid": s.get("uuid"),
                "name": s.get("name", ""),
                "state": step_state.get("name", "UNKNOWN"),
                "result": step_state.get("result", {}).get("name", "") if step_state.get("result") else "",
                "started_on": s.get("started_on"),
                "completed_on": s.get("completed_on"),
            })

        state = pipeline.get("state", {})
        return {
            "uuid": pipeline.get("uuid"),
            "build_number": pipeline.get("build_number"),
            "state": state.get("name", "UNKNOWN"),
            "result": state.get("result", {}).get("name", "") if state.get("result") else "",
            "branch": pipeline.get("target", {}).get("ref_name", ""),
            "trigger": pipeline.get("trigger", {}).get("name", ""),
            "created_on": pipeline.get("created_on"),
            "completed_on": pipeline.get("completed_on"),
            "duration_seconds": pipeline.get("build_seconds_used"),
            "steps": steps,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pipeline_step_log(
    repo_slug: str, pipeline_uuid: str, step_uuid: str, workspace: str = "",
) -> dict:
    """
    Get the log output of a specific pipeline step.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pipeline_uuid: Pipeline UUID
        step_uuid: Step UUID (get from bb_get_pipeline results)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        Raw log text of the pipeline step

    Example:
        bb_get_pipeline_step_log("my-repo", "{pipeline-uuid}", "{step-uuid}")
    """
    try:
        client = get_client()
        ws = workspace or None
        log_text = client.get_pipeline_step_log(repo_slug, pipeline_uuid, step_uuid, workspace=ws)
        return {"log": log_text}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== SERVER ENTRY POINT =====

def main():
    try:
        get_client()
        print("Bitbucket MCP Server starting...", file=sys.stderr)
        print(f"Workspace: {os.getenv('BITBUCKET_WORKSPACE', '(not set)')}", file=sys.stderr)
        print("Server ready!", file=sys.stderr)
        mcp.run()
    except ValueError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Fatal Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Verify module loads**

Run: `uv run python -c "from bitbucket_mcp.server import mcp; print('OK:', len(mcp._tool_manager._tools), 'tools')"`
Expected: `OK: 14 tools`

**Step 3: Commit**

```bash
git add bitbucket_mcp/server.py
git commit -m "feat: add MCP server with all 14 Bitbucket tools"
```

---

### Task 7: Update __init__.py and Smoke Test

**Files:**
- Modify: `bitbucket_mcp/__init__.py`

**Step 1: Update __init__.py to export client and main**

```python
"""
MCP Server for Bitbucket Cloud REST API integration.
"""

from bitbucket_mcp.client import BitbucketClient
from bitbucket_mcp.server import main

__version__ = "0.1.0"
__all__ = ["BitbucketClient", "main"]
```

**Step 2: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

**Step 3: Smoke test — verify server starts (will fail without env vars, that's ok)**

Run: `BITBUCKET_EMAIL=test BITBUCKET_API_TOKEN=test BITBUCKET_WORKSPACE=test timeout 3 uv run bitbucket-mcp 2>&1 || true`
Expected: Output includes "Bitbucket MCP Server starting..." (may timeout or fail on connection, but should not crash on import)

**Step 4: Commit**

```bash
git add bitbucket_mcp/__init__.py
git commit -m "feat: update package exports and smoke test"
```

---

### Task 8: Clean Up and Documentation

**Files:**
- Delete: `bitbucket-api-reference.md` (research artifact, not needed in final package)
- Verify: `.gitignore` exists (add if missing)

**Step 1: Add .gitignore**

```
__pycache__/
*.egg-info/
.env
dist/
build/
.pytest_cache/
```

**Step 2: Clean up research artifact**

```bash
rm bitbucket-api-reference.md
```

**Step 3: Run full test suite one final time**

Run: `uv run pytest tests/ -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add .gitignore
git rm bitbucket-api-reference.md
git commit -m "chore: add .gitignore and clean up research artifacts"
```

---

### Task 9: Add to MCP Configuration

**Manual step** — the user needs to add the bitbucket server entry to their `~/.claude/mcp.json` (or wherever their MCP config lives):

```json
"bitbucket": {
  "command": "uv",
  "args": [
    "run",
    "--directory",
    "/path/to/bitbucket-mcp",
    "bitbucket-mcp"
  ],
  "env": {
    "BITBUCKET_EMAIL": "your-email@example.com",
    "BITBUCKET_API_TOKEN": "<your-api-token>",
    "BITBUCKET_WORKSPACE": "my-workspace"
  }
}
```

Then restart Claude Desktop / Claude Code to pick up the new server.

**Verify:** Try calling `bb_list_pull_requests("my-repo")` or `bb_get_pull_request("my-repo", 302)` to confirm it works against the real API.
