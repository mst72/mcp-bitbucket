"""Bitbucket Server/Data Center REST API client."""

import requests
from typing import Any, Dict, List, Optional, Set

from bitbucket_mcp.errors import BadRequestError, BitbucketError, handle_api_error


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

    @staticmethod
    def _normalize_comment_anchor(anchor: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not anchor:
            return None

        normalized = {
            "path": anchor.get("path") or anchor.get("toPath") or anchor.get("srcPath"),
            "line": anchor.get("line") or anchor.get("lineNumber") or anchor.get("to"),
            "lineType": anchor.get("lineType"),
        }

        if all(value is None for value in normalized.values()):
            return anchor
        return normalized

    def _upsert_activity_comment(
        self,
        comment: Optional[Dict[str, Any]],
        anchor: Optional[Dict[str, Any]],
        comments_by_id: Dict[int, Dict[str, Any]],
        ordered_ids: List[int],
        parent_to_children: Dict[int, Set[int]],
        parent_id: Optional[int] = None,
    ) -> None:
        if not comment:
            return

        comment_id = comment.get("id")
        if comment_id is None:
            return

        comment_data = dict(comment)
        normalized_anchor = self._normalize_comment_anchor(anchor or comment.get("anchor"))
        if normalized_anchor and "anchor" not in comment_data:
            comment_data["anchor"] = normalized_anchor
        if parent_id is not None and "parent" not in comment_data:
            comment_data["parent"] = {"id": parent_id}

        actual_parent_id = comment_data.get("parent", {}).get("id")
        if actual_parent_id is not None:
            parent_to_children.setdefault(actual_parent_id, set()).add(comment_id)

        existing = comments_by_id.get(comment_id)
        if existing is None:
            comments_by_id[comment_id] = comment_data
            ordered_ids.append(comment_id)
        else:
            existing.update(comment_data)
            comment_data = existing

        for reply in comment.get("comments", []):
            self._upsert_activity_comment(
                reply,
                comment_data.get("anchor"),
                comments_by_id,
                ordered_ids,
                parent_to_children,
                parent_id=comment_id,
            )

    def _remove_comment_subtree(
        self,
        comment_id: int,
        comments_by_id: Dict[int, Dict[str, Any]],
        ordered_ids: List[int],
        parent_to_children: Dict[int, Set[int]],
    ) -> None:
        for child_id in list(parent_to_children.get(comment_id, set())):
            self._remove_comment_subtree(child_id, comments_by_id, ordered_ids, parent_to_children)

        comment = comments_by_id.pop(comment_id, None)
        ordered_ids[:] = [cid for cid in ordered_ids if cid != comment_id]

        if comment:
            parent_id = comment.get("parent", {}).get("id")
            if parent_id is not None and parent_id in parent_to_children:
                parent_to_children[parent_id].discard(comment_id)
                if not parent_to_children[parent_id]:
                    del parent_to_children[parent_id]

        parent_to_children.pop(comment_id, None)

    def _consume_activity_page(
        self,
        activities: Dict[str, Any],
        comments_by_id: Dict[int, Dict[str, Any]],
        ordered_ids: List[int],
        parent_to_children: Dict[int, Set[int]],
    ) -> None:
        for activity in activities.get("values", []):
            if activity.get("action") != "COMMENTED":
                continue

            comment = activity.get("comment")
            if not comment:
                continue

            comment_id = comment.get("id")
            if activity.get("commentAction") == "DELETED":
                if comment_id in comments_by_id:
                    self._remove_comment_subtree(
                        comment_id,
                        comments_by_id,
                        ordered_ids,
                        parent_to_children,
                    )
                continue

            self._upsert_activity_comment(
                comment,
                activity.get("commentAnchor"),
                comments_by_id,
                ordered_ids,
                parent_to_children,
            )

    def _comments_from_activities(
        self,
        repo_slug: str,
        pr_id: int,
        start: int,
        limit: int,
        project: Optional[str] = None,
    ) -> Dict[str, Any]:
        comments_by_id: Dict[int, Dict[str, Any]] = {}
        ordered_ids: List[int] = []
        parent_to_children: Dict[int, Set[int]] = {}
        activities_url = f"{self._repo_url(repo_slug, project)}/pull-requests/{pr_id}/activities"
        activity_start = 0
        activity_limit = max(limit, 50)

        while True:
            activities = self._request(
                "GET",
                activities_url,
                params={"start": activity_start, "limit": activity_limit},
            )
            self._consume_activity_page(
                activities,
                comments_by_id,
                ordered_ids,
                parent_to_children,
            )

            if activities.get("isLastPage", True):
                break

            next_page_start = activities.get("nextPageStart")
            if next_page_start is None:
                batch_size = len(activities.get("values", []))
                if batch_size == 0:
                    break
                next_page_start = activity_start + batch_size
            activity_start = next_page_start

        total_comments = len(ordered_ids)
        page_comment_ids = ordered_ids[start:start + limit]

        return {
            "size": total_comments,
            "limit": limit,
            "isLastPage": start + len(page_comment_ids) >= total_comments,
            "start": start,
            "values": [comments_by_id[cid] for cid in page_comment_ids if cid in comments_by_id],
        }

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
        try:
            return self._request("GET", url, params=params)
        except BadRequestError as e:
            if "path query parameter is required" not in e.message.lower():
                raise

            return self._comments_from_activities(
                repo_slug,
                pr_id,
                start=start,
                limit=limit,
                project=project,
            )

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
