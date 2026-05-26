# Bitbucket MCP Server — Design

## Goal

MCP server for Bitbucket Cloud that enables Claude to manage the full PR lifecycle: create, review, comment, update, check pipelines, and merge.

## Architecture

Standalone Python + FastMCP server following the same patterns as jira-confluence and trello MCP servers in this monorepo.

```
bitbucket-mcp/
├── bitbucket_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py      # FastMCP server + 14 tools
│   ├── client.py      # HTTP client for Bitbucket Cloud API 2.0
│   └── errors.py      # Error classes with to_dict() for MCP responses
├── pyproject.toml
└── .env.example
```

## Auth

- Basic Auth (email + app password) via `requests.Session`
- Env vars: `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`, `BITBUCKET_WORKSPACE`
- Lazy-loaded singleton client via `get_client()`
- Base URL: `https://api.bitbucket.org/2.0`

## Tools (14)

### Pull Requests (6)

| Tool | Method | Endpoint | Description |
|------|--------|----------|-------------|
| `bb_list_pull_requests` | GET | `/repositories/{workspace}/{repo}/pullrequests` | List PRs, filter by state (OPEN/MERGED/DECLINED) |
| `bb_get_pull_request` | GET | `/repositories/{workspace}/{repo}/pullrequests/{id}` | PR details + participants/approvals |
| `bb_create_pull_request` | POST | `/repositories/{workspace}/{repo}/pullrequests` | Create PR with source/dest branch, title, description, reviewers |
| `bb_update_pull_request` | PUT | `/repositories/{workspace}/{repo}/pullrequests/{id}` | Update title/description |
| `bb_merge_pull_request` | POST | `.../pullrequests/{id}/merge` | Merge with strategy (merge_commit/squash/fast_forward) |
| `bb_decline_pull_request` | POST | `.../pullrequests/{id}/decline` | Decline PR |

### Comments (3)

| Tool | Method | Endpoint | Description |
|------|--------|----------|-------------|
| `bb_list_pr_comments` | GET | `.../pullrequests/{id}/comments` | List PR comments |
| `bb_add_pr_comment` | POST | `.../pullrequests/{id}/comments` | General comment |
| `bb_add_pr_inline_comment` | POST | `.../pullrequests/{id}/comments` | Inline comment on file/line |

### Review (2)

| Tool | Method | Endpoint | Description |
|------|--------|----------|-------------|
| `bb_approve_pull_request` | POST | `.../pullrequests/{id}/approve` | Approve PR |
| `bb_get_pr_diff` | GET | `.../pullrequests/{id}/diff` | Raw diff text |

### Pipelines (3)

| Tool | Method | Endpoint | Description |
|------|--------|----------|-------------|
| `bb_list_pipelines` | GET | `/repositories/{workspace}/{repo}/pipelines/` | List pipelines (newest first) |
| `bb_get_pipeline` | GET | `.../pipelines/{uuid}` | Pipeline status + steps |
| `bb_get_pipeline_step_log` | GET | `.../pipelines/{uuid}/steps/{step_uuid}/log` | Step logs |

## Tool Parameters

Every tool takes `repo_slug` (required) and optional `workspace` (defaults to `BITBUCKET_WORKSPACE` env var). This allows working with multiple repos/workspaces without reconfiguration.

## Response Format

Same pattern as jira-confluence:
- Success: `{"success": true, ...data}`
- Error: `{"error": "message", "status_code": 401, "details": "..."}`
- Lists: `{"count": N, "items": [...]}`

## MCP Configuration

```json
"bitbucket": {
  "command": "uv",
  "args": ["run", "--directory", "/path/to/bitbucket-mcp", "bitbucket-mcp"],
  "env": {
    "BITBUCKET_EMAIL": "your-email@example.com",
    "BITBUCKET_API_TOKEN": "...",
    "BITBUCKET_WORKSPACE": "my-workspace"
  }
}
```

## Dependencies

- `mcp>=1.20.0`
- `requests>=2.31.0`
- `python-dotenv>=1.0.0`

## Key API Notes

- Bitbucket Cloud REST API 2.0 base: `https://api.bitbucket.org/2.0`
- Inline comments use `inline.path` (required), `inline.to` (new-side line), `inline.from` (old-side line)
- Pipeline `q` filter not supported — use `sort=-created_on` and filter client-side
- Pipeline states: PENDING -> RUNNING -> COMPLETED (results: SUCCESSFUL/FAILED/ERROR/STOPPED)
- Merge strategies: `merge_commit`, `squash`, `fast_forward`
- Approvals/reviewers come from `participants` array on PR object (no separate endpoint)
- Diff endpoint returns `text/plain` — need `Accept: text/plain` header
