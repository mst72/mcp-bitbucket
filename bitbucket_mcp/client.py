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

    # ===== REPOSITORIES =====

    def list_repositories(
        self, page: int = 1, pagelen: int = 25,
        role: str = "", workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        ws = workspace or self.workspace
        url = f"{self.base_url}/repositories/{ws}"
        params: Dict[str, Any] = {"page": page, "pagelen": pagelen, "sort": "-updated_on"}
        if role:
            params["role"] = role
        return self._request("GET", url, params=params)

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
