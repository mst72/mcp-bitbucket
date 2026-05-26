# Bitbucket MCP Server

MCP server for Bitbucket Cloud that enables Claude to manage the full pull request lifecycle: list repos, create/review/comment/merge PRs, and check pipeline status.

## Tools (15)

| Tool | Description |
|------|-------------|
| `bb_list_repositories` | List repositories in a workspace |
| `bb_list_pull_requests` | List PRs with state filtering (OPEN/MERGED/DECLINED) |
| `bb_get_pull_request` | PR details with reviewers and approval status |
| `bb_create_pull_request` | Create a PR with title, branches, description, reviewers |
| `bb_update_pull_request` | Update PR title and/or description |
| `bb_merge_pull_request` | Merge a PR (merge_commit/squash/fast_forward) |
| `bb_decline_pull_request` | Decline (close) a PR |
| `bb_list_pr_comments` | List comments on a PR |
| `bb_add_pr_comment` | Add a general comment or reply |
| `bb_add_pr_inline_comment` | Comment on a specific file/line in the diff |
| `bb_approve_pull_request` | Approve a PR |
| `bb_get_pr_diff` | Get raw unified diff |
| `bb_list_pipelines` | List recent pipelines |
| `bb_get_pipeline` | Pipeline details with steps |
| `bb_get_pipeline_step_log` | Log output of a pipeline step |

## Setup

### 1. Create a Bitbucket API Token

> **Important:** As of September 2025, Bitbucket App Passwords are deprecated. You need an **API token with scopes**.

1. Go to [Atlassian Account Settings](https://id.atlassian.com) > **Security**
2. Click **"Create API token with scopes"** (not the plain "Create API token" button — that one doesn't work for Bitbucket)
3. Name the token, click Next
4. **Select "Bitbucket" as the application**
5. Assign scopes:
   - **Repositories**: Read
   - **Pull Requests**: Read, Write
   - **Pipelines**: Read
6. Create and copy the token (shown only once)

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```
BITBUCKET_EMAIL=your-email@example.com
BITBUCKET_API_TOKEN=your-scoped-api-token
BITBUCKET_WORKSPACE=your-default-workspace
```

### 3. Add to Claude Code

Create `.mcp.json` in the project root (or add to your existing one):

```json
{
  "mcpServers": {
    "bitbucket": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/this/project",
        "bitbucket-mcp"
      ],
      "env": {
        "BITBUCKET_EMAIL": "your-email@example.com",
        "BITBUCKET_API_TOKEN": "your-scoped-api-token",
        "BITBUCKET_WORKSPACE": "your-workspace"
      }
    }
  }
}
```

Restart Claude Code to pick up the new server.

### 4. Test with MCP Inspector (optional)

```bash
npx @modelcontextprotocol/inspector uv run --directory /path/to/this/project bitbucket-mcp
```

## Development

```bash
# Install dependencies
uv sync --dev

# Run tests
uv run pytest tests/ -v
```

## Tech Stack

- Python 3.10+
- [FastMCP](https://github.com/jlowin/fastmcp) (`mcp>=1.20.0`)
- `requests` for HTTP
- Bitbucket Cloud REST API 2.0
