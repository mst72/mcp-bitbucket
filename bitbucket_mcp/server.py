"""MCP Server for Bitbucket Server/Data Center integration."""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
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
        base_url = os.getenv("BITBUCKET_BASE_URL")
        api_token = os.getenv("BITBUCKET_API_TOKEN")
        project = os.getenv("BITBUCKET_PROJECT", "")

        if not all([base_url, api_token]):
            missing = []
            if not base_url:
                missing.append("BITBUCKET_BASE_URL")
            if not api_token:
                missing.append("BITBUCKET_API_TOKEN")
            raise ValueError(f"Missing required env vars: {', '.join(missing)}")

        _client = BitbucketClient(base_url, api_token, project)
    return _client


def _get_username() -> str:
    username = os.getenv("BITBUCKET_USERNAME", "")
    if not username:
        raise ValueError(
            "BITBUCKET_USERNAME env var is required for approvals. "
            "Set it to your Bitbucket username/slug."
        )
    return username


def _ts_to_iso(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()


# ===== PROJECT TOOLS =====

@mcp.tool()
def bb_list_projects(start: int = 0, limit: int = 50) -> dict:
    """
    List all Bitbucket projects accessible to the current user.

    Args:
        start: Offset for pagination (default: 0)
        limit: Results per page (default: 50)

    Returns:
        List of projects with key, name, and description

    Example:
        bb_list_projects()
    """
    try:
        client = get_client()
        result = client.list_projects(start=start, limit=limit)

        projects = []
        for p in result.get("values", []):
            link = ""
            self_links = p.get("links", {}).get("self", [])
            if self_links:
                link = self_links[0].get("href", "")
            projects.append({
                "key": p.get("key"),
                "name": p.get("name"),
                "description": p.get("description", ""),
                "link": link,
            })

        return {
            "count": len(projects),
            "total": result.get("size", len(projects)),
            "is_last_page": result.get("isLastPage", True),
            "projects": projects,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== REPOSITORY TOOLS =====

@mcp.tool()
def bb_list_repositories(
    start: int = 0, limit: int = 25, project: str = "",
) -> dict:
    """
    List repositories in a Bitbucket project.

    Args:
        start: Offset for pagination (default: 0)
        limit: Results per page, max 100 (default: 25)
        project: Bitbucket project key (e.g., "PMC"). Optional, uses default from env.
                 If neither is set, lists all repos accessible to the current user.

    Returns:
        List of repositories with name, slug, description, and project key

    Example:
        bb_list_repositories()
        bb_list_repositories(project="PMC", limit=50)
    """
    try:
        client = get_client()
        proj = project or None
        result = client.list_repositories(start=start, limit=limit, project=proj)

        repos = []
        for r in result.get("values", []):
            link = ""
            self_links = r.get("links", {}).get("self", [])
            if self_links:
                link = self_links[0].get("href", "")
            repos.append({
                "slug": r.get("slug"),
                "name": r.get("name"),
                "description": r.get("description", ""),
                "project": r.get("project", {}).get("key", ""),
                "is_public": r.get("public", False),
                "link": link,
            })

        return {
            "count": len(repos),
            "total": result.get("size", len(repos)),
            "is_last_page": result.get("isLastPage", True),
            "repositories": repos,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== PULL REQUEST TOOLS =====

@mcp.tool()
def bb_list_pull_requests(
    repo_slug: str, state: str = "OPEN", start: int = 0,
    limit: int = 25, project: str = "",
) -> dict:
    """
    List pull requests for a repository.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        state: PR state filter — OPEN, MERGED, DECLINED, ALL (default: OPEN)
        start: Offset for pagination (default: 0)
        limit: Results per page (default: 25)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        List of pull requests with id, title, state, author, branches, dates

    Example:
        bb_list_pull_requests("my-repo")
        bb_list_pull_requests("my-repo", state="MERGED", limit=10)
    """
    try:
        client = get_client()
        proj = project or None
        result = client.list_pull_requests(repo_slug, state=state, start=start, limit=limit, project=proj)

        prs = []
        for pr in result.get("values", []):
            link = ""
            self_links = pr.get("links", {}).get("self", [])
            if self_links:
                link = self_links[0].get("href", "")
            prs.append({
                "id": pr.get("id"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "author": pr.get("author", {}).get("user", {}).get("displayName", "Unknown"),
                "source_branch": pr.get("fromRef", {}).get("displayId"),
                "destination_branch": pr.get("toRef", {}).get("displayId"),
                "created_on": _ts_to_iso(pr.get("createdDate")),
                "updated_on": _ts_to_iso(pr.get("updatedDate")),
                "comment_count": pr.get("properties", {}).get("commentCount", 0),
                "link": link,
            })

        return {
            "count": len(prs),
            "total": result.get("size", len(prs)),
            "is_last_page": result.get("isLastPage", True),
            "pull_requests": prs,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pull_request(repo_slug: str, pr_id: int, project: str = "") -> dict:
    """
    Get detailed information about a pull request including reviewers and approvals.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID (e.g., 42)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Full PR details: title, description, state, author, branches, reviewers,
        participants with approval status, and link

    Example:
        bb_get_pull_request("my-repo", 42)
    """
    try:
        client = get_client()
        proj = project or None
        pr = client.get_pull_request(repo_slug, pr_id, project=proj)

        reviewers = []
        for r in pr.get("reviewers", []):
            reviewers.append({
                "user": r.get("user", {}).get("displayName", "Unknown"),
                "slug": r.get("user", {}).get("name", ""),
                "approved": r.get("approved", False),
                "status": r.get("status", "UNAPPROVED"),
            })

        link = ""
        self_links = pr.get("links", {}).get("self", [])
        if self_links:
            link = self_links[0].get("href", "")

        return {
            "id": pr.get("id"),
            "title": pr.get("title"),
            "description": pr.get("description", ""),
            "state": pr.get("state"),
            "author": pr.get("author", {}).get("user", {}).get("displayName", "Unknown"),
            "source_branch": pr.get("fromRef", {}).get("displayId"),
            "destination_branch": pr.get("toRef", {}).get("displayId"),
            "created_on": _ts_to_iso(pr.get("createdDate")),
            "updated_on": _ts_to_iso(pr.get("updatedDate")),
            "reviewers": reviewers,
            "link": link,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_create_pull_request(
    repo_slug: str, title: str, source_branch: str,
    destination_branch: str = "main", description: str = "",
    reviewers: Optional[list[str]] = None, project: str = "",
) -> dict:
    """
    Create a new pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        title: PR title
        source_branch: Source branch name (e.g., "feature/my-feature")
        destination_branch: Target branch name (default: "main")
        description: PR description text
        reviewers: Optional list of reviewer usernames/slugs (e.g., ["jsmith", "adoe"])
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Created PR data with id, title, state, and link

    Example:
        bb_create_pull_request("my-repo", "Add login feature", "feature/login")
    """
    try:
        client = get_client()
        proj = project or None
        result = client.create_pull_request(
            repo_slug, title=title, source_branch=source_branch,
            destination_branch=destination_branch, description=description,
            reviewers=reviewers, project=proj,
        )
        link = ""
        self_links = result.get("links", {}).get("self", [])
        if self_links:
            link = self_links[0].get("href", "")
        return {
            "success": True,
            "id": result.get("id"),
            "title": result.get("title"),
            "state": result.get("state"),
            "link": link,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_update_pull_request(
    repo_slug: str, pr_id: int, title: Optional[str] = None,
    description: Optional[str] = None, project: str = "",
) -> dict:
    """
    Update a pull request's title and/or description.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        title: New title (optional, only updates if provided)
        description: New description (optional, only updates if provided)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Updated PR data

    Example:
        bb_update_pull_request("my-repo", 42, description="Updated description")
    """
    try:
        client = get_client()
        proj = project or None
        result = client.update_pull_request(repo_slug, pr_id, title=title, description=description, project=proj)
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
    repo_slug: str, pr_id: int, message: str = "", project: str = "",
) -> dict:
    """
    Merge a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        message: Optional merge commit message
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Merged PR data with state=MERGED

    Example:
        bb_merge_pull_request("my-repo", 42)
    """
    try:
        client = get_client()
        proj = project or None
        msg = message or None
        result = client.merge_pull_request(repo_slug, pr_id, message=msg, project=proj)
        return {
            "success": True,
            "id": result.get("id"),
            "state": result.get("state"),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_decline_pull_request(repo_slug: str, pr_id: int, project: str = "") -> dict:
    """
    Decline (close without merging) a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Declined PR data with state=DECLINED

    Example:
        bb_decline_pull_request("my-repo", 42)
    """
    try:
        client = get_client()
        proj = project or None
        result = client.decline_pull_request(repo_slug, pr_id, project=proj)
        return {"success": True, "id": result.get("id"), "state": result.get("state")}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== COMMENT TOOLS =====

@mcp.tool()
def bb_list_pr_comments(
    repo_slug: str, pr_id: int, start: int = 0,
    limit: int = 50, project: str = "",
) -> dict:
    """
    List comments on a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        start: Offset for pagination (default: 0)
        limit: Results per page (default: 50)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        List of comments with author, text, and inline anchor (if any)

    Example:
        bb_list_pr_comments("my-repo", 42)
    """
    try:
        client = get_client()
        proj = project or None
        result = client.list_pr_comments(repo_slug, pr_id, start=start, limit=limit, project=proj)

        comments = []
        for c in result.get("values", []):
            comment = {
                "id": c.get("id"),
                "author": c.get("author", {}).get("displayName", "Unknown"),
                "text": c.get("text", ""),
                "created_on": _ts_to_iso(c.get("createdDate")),
            }
            anchor = c.get("anchor")
            if anchor:
                comment["inline"] = {
                    "path": anchor.get("path"),
                    "line": anchor.get("line"),
                    "line_type": anchor.get("lineType"),
                }
            parent = c.get("parent")
            if parent:
                comment["parent_id"] = parent.get("id")
            comments.append(comment)

        return {
            "count": len(comments),
            "total": result.get("size", len(comments)),
            "is_last_page": result.get("isLastPage", True),
            "comments": comments,
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_add_pr_comment(
    repo_slug: str, pr_id: int, text: str,
    parent_id: int = 0, project: str = "",
) -> dict:
    """
    Add a general comment to a pull request, or reply to an existing comment.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        text: Comment text
        parent_id: ID of comment to reply to (optional, 0 = top-level comment)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Created comment data

    Example:
        bb_add_pr_comment("my-repo", 42, "Looks good overall!")
        bb_add_pr_comment("my-repo", 42, "Fixed, thanks!", parent_id=7)
    """
    try:
        client = get_client()
        proj = project or None
        pid = parent_id if parent_id else None
        result = client.add_pr_comment(repo_slug, pr_id, text, parent_id=pid, project=proj)
        return {
            "success": True,
            "id": result.get("id"),
            "author": result.get("author", {}).get("displayName", "Unknown"),
            "text": result.get("text", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_add_pr_inline_comment(
    repo_slug: str, pr_id: int, text: str, file_path: str,
    line: int = 0, line_type: str = "ADDED", project: str = "",
) -> dict:
    """
    Add an inline comment on a specific file/line in a pull request diff.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        text: Comment text
        file_path: File path relative to repo root (e.g., "src/main.py")
        line: Line number to comment on (0 = file-level comment)
        line_type: Line type — ADDED, REMOVED, CONTEXT (default: ADDED)
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Created inline comment data

    Example:
        bb_add_pr_inline_comment("my-repo", 42, "Use a constant here", "src/main.py", line=42)
    """
    try:
        client = get_client()
        proj = project or None
        ln = line if line else None
        result = client.add_pr_inline_comment(
            repo_slug, pr_id, text, file_path,
            line=ln, line_type=line_type, project=proj,
        )
        anchor = result.get("anchor", {})
        return {
            "success": True,
            "id": result.get("id"),
            "file": anchor.get("path", file_path),
            "line": anchor.get("line"),
            "text": result.get("text", ""),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== REVIEW TOOLS =====

@mcp.tool()
def bb_approve_pull_request(
    repo_slug: str, pr_id: int, user_slug: str = "", project: str = "",
) -> dict:
    """
    Approve a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        user_slug: Your Bitbucket username/slug. Optional if BITBUCKET_USERNAME env var is set.
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Approval confirmation

    Example:
        bb_approve_pull_request("my-repo", 42)
        bb_approve_pull_request("my-repo", 42, user_slug="jsmith")
    """
    try:
        client = get_client()
        proj = project or None
        slug = user_slug or _get_username()
        result = client.approve_pull_request(repo_slug, pr_id, slug, project=proj)
        return {
            "success": True,
            "approved": result.get("approved", True),
            "status": result.get("status", "APPROVED"),
            "user": result.get("user", {}).get("displayName", slug),
        }
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


@mcp.tool()
def bb_get_pr_diff(repo_slug: str, pr_id: int, project: str = "") -> dict:
    """
    Get the raw unified diff of a pull request.

    Args:
        repo_slug: Repository slug (e.g., "my-repo")
        pr_id: Pull request ID
        project: Bitbucket project key (optional, uses default from env)

    Returns:
        Raw diff text showing all file changes in unified diff format

    Example:
        bb_get_pr_diff("my-repo", 42)
    """
    try:
        client = get_client()
        proj = project or None
        diff_text = client.get_pr_diff(repo_slug, pr_id, project=proj)
        return {"diff": diff_text}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== META TOOLS =====

FEEDBACK_DIR = Path(
    os.getenv("BITBUCKET_FEEDBACK_DIR", "")
    or os.path.join(Path.home(), ".bitbucket-mcp", "feedback")
)


def _slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]


@mcp.tool()
def bb_submit_feedback(
    title: str, description: str, category: str = "idea",
) -> dict:
    """
    Submit feedback or an improvement idea for the Bitbucket MCP server.

    Use this tool when you notice a missing feature, a bug, or have an idea
    for improving the MCP server tools. Feedback is saved as a local markdown
    file for the maintainer to review later.

    Args:
        title: Short summary of the feedback (e.g., "Add bb_get_pr_files tool")
        description: Detailed description of the idea, problem, or suggestion
        category: Type of feedback — idea, bug, feature, improvement (default: "idea")

    Returns:
        Confirmation with the saved file path

    Example:
        bb_submit_feedback("Add PR file list tool", "No way to list changed files without fetching the full diff", category="feature")
    """
    try:
        if not title or not title.strip():
            return {"error": "Title is required"}
        if not description or not description.strip():
            return {"error": "Description is required"}

        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        slug = _slugify(title)
        filename = f"{now.strftime('%Y-%m-%dT%H%M%S')}-{slug}.md"
        filepath = FEEDBACK_DIR / filename

        content = (
            f"---\n"
            f'title: "{title}"\n'
            f"category: {category}\n"
            f"status: open\n"
            f"created: {now.isoformat()}\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{description}\n"
        )

        filepath.write_text(content, encoding="utf-8")
        return {"success": True, "file": filename, "path": str(filepath)}
    except OSError as e:
        return {"error": f"Failed to write feedback: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


# ===== SERVER ENTRY POINT =====

def main():
    try:
        get_client()
        print("Bitbucket MCP Server starting...", file=sys.stderr)
        print(f"Project: {os.getenv('BITBUCKET_PROJECT', '(not set)')}", file=sys.stderr)
        print(f"Base URL: {os.getenv('BITBUCKET_BASE_URL', '(not set)')}", file=sys.stderr)
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
