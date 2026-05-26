"""Bitbucket Server/Data Center REST API client."""

import requests
from typing import Any, Dict, List, Optional

from bitbucket_mcp.errors import BitbucketError, handle_api_error


class BitbucketClient:

    def __init__(self, base_url: str, api_token: str, project: str):
        self.base_url = base_url.rstrip("/") + "/rest/api/1.0"
        self.project = project
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _repo_url(self, repo_slug: str, project: Optional[str] = None) -> str:
        proj = project or self.project
        return f"{self.base_url}/projects/{proj}/repos/{repo_slug}"

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

    # ===== PROJECTS =====

    def list_projects(self, start: int = 0, limit: int = 50) -> Dict[str, Any]:
        url = f"{self.base_url}/projects"
        params: Dict[str, Any] = {"start": start, "limit": limit}
        return self._request("GET", url, params=params)

    # ===== REPOSITORIES =====

    def list_repositories(
        self, start: int = 0, limit: int = 25, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        if project or self.project:
            proj = project or self.project
            url = f"{self.base_url}/projects/{proj}/repos"
        else:
            url = f"{self.base_url}/repos"
        params: Dict[str, Any] = {"start": start, "limit": limit}
        return self._request("GET", url, params=params)

    # ===== PULL REQUESTS =====

    def list_pull_requests(
        self, repo_slug: str, state: str = "OPEN",
        start: int = 0, limit: int = 25, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests"
        params = {"state": state, "start": start, "limit": limit}
        return self._request("GET", url, params=params)

    def get_pull_request(
        self, repo_slug: str, pr_id: int, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}"
        return self._request("GET", url)

    def create_pull_request(
        self, repo_slug: str, title: str, source_branch: str,
        destination_branch: str = "main", description: str = "",
        reviewers: Optional[List[str]] = None,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        proj = project or self.project
        url = f"{self._repo_url(repo_slug, project)}/pull-requests"
        payload: Dict[str, Any] = {
            "title": title,
            "description": description,
            "fromRef": {
                "id": f"refs/heads/{source_branch}",
                "repository": {"slug": repo_slug, "project": {"key": proj}},
            },
            "toRef": {
                "id": f"refs/heads/{destination_branch}",
                "repository": {"slug": repo_slug, "project": {"key": proj}},
            },
        }
        if reviewers:
            payload["reviewers"] = [{"user": {"name": slug}} for slug in reviewers]
        return self._request("POST", url, json=payload)

    def update_pull_request(
        self, repo_slug: str, pr_id: int, title: Optional[str] = None,
        description: Optional[str] = None, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_pull_request(repo_slug, pr_id, project=project)
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}"
        payload: Dict[str, Any] = {
            "id": pr_id,
            "version": existing["version"],
            "title": title if title is not None else existing["title"],
            "description": description if description is not None else existing.get("description", ""),
            "toRef": existing["toRef"],
            "reviewers": existing.get("reviewers", []),
        }
        return self._request("PUT", url, json=payload)

    def merge_pull_request(
        self, repo_slug: str, pr_id: int, message: Optional[str] = None,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_pull_request(repo_slug, pr_id, project=project)
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/merge"
        params: Dict[str, Any] = {"version": existing["version"]}
        payload: Dict[str, Any] = {}
        if message:
            payload["message"] = message
        return self._request("POST", url, params=params, json=payload)

    def decline_pull_request(
        self, repo_slug: str, pr_id: int, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        existing = self.get_pull_request(repo_slug, pr_id, project=project)
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/decline"
        params = {"version": existing["version"]}
        return self._request("POST", url, params=params)

    # ===== COMMENTS =====

    def list_pr_comments(
        self, repo_slug: str, pr_id: int, start: int = 0,
        limit: int = 50, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/comments"
        params = {"start": start, "limit": limit}
        return self._request("GET", url, params=params)

    def add_pr_comment(
        self, repo_slug: str, pr_id: int, text: str,
        parent_id: Optional[int] = None, project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/comments"
        payload: Dict[str, Any] = {"text": text}
        if parent_id:
            payload["parent"] = {"id": parent_id}
        return self._request("POST", url, json=payload)

    def add_pr_inline_comment(
        self, repo_slug: str, pr_id: int, text: str, file_path: str,
        line: Optional[int] = None, line_type: str = "ADDED",
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/comments"
        payload: Dict[str, Any] = {
            "text": text,
            "anchor": {
                "path": file_path,
                "fileType": "TO",
                "lineType": line_type,
            },
        }
        if line is not None:
            payload["anchor"]["line"] = line
        return self._request("POST", url, json=payload)

    # ===== REVIEW =====

    def approve_pull_request(
        self, repo_slug: str, pr_id: int, user_slug: str,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/participants/{user_slug}"
        payload = {"user": {"name": user_slug}, "approved": True, "status": "APPROVED"}
        return self._request("PUT", url, json=payload)

    def get_pr_diff(
        self, repo_slug: str, pr_id: int, project: Optional[str] = None,
    ) -> str:
        url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/diff"
        return self._request("GET", url, accept="text/plain")
