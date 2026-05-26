"""MCP Server for Bitbucket Cloud integration."""

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


# ===== REPOSITORY TOOLS =====

@mcp.tool()
def bb_list_repositories(
    page: int = 1, pagelen: int = 25, role: str = "", workspace: str = "",
) -> dict:
    """
    List repositories in a Bitbucket workspace.

    Args:
        page: Page number for pagination (default: 1)
        pagelen: Results per page, max 100 (default: 25)
        role: Filter by your role — owner, admin, contributor, member (optional)
        workspace: Bitbucket workspace (optional, uses default from env)

    Returns:
        List of repositories with name, slug, description, language, and updated date

    Example:
        bb_list_repositories()
        bb_list_repositories(role="contributor", pagelen=50)
    """
    try:
        client = get_client()
        ws = workspace or None
        result = client.list_repositories(page=page, pagelen=pagelen, role=role, workspace=ws)

        repos = []
        for r in result.get("values", []):
            repos.append({
                "slug": r.get("slug"),
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "description": r.get("description", ""),
                "language": r.get("language", ""),
                "is_private": r.get("is_private", True),
                "updated_on": r.get("updated_on"),
                "link": r.get("links", {}).get("html", {}).get("href", ""),
            })

        return {"count": len(repos), "total": result.get("size", len(repos)), "page": page, "repositories": repos}
    except BitbucketError as e:
        return e.to_dict()
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}


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
                "uuid": p.get("user", {}).get("uuid", ""),
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
