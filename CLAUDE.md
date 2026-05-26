# Bitbucket MCP Server

## Project

MCP server for Bitbucket Cloud REST API 2.0. Python + FastMCP. 16 tools: PR lifecycle, comments, reviews, pipelines, feedback collection.

## Structure

```
bitbucket_mcp/
  server.py    — FastMCP server, all tools, get_client() singleton
  client.py    — BitbucketClient HTTP wrapper, all API methods
  errors.py    — BitbucketError hierarchy, handle_api_error()
tests/
  test_client.py — 18 tests (responses library for HTTP mocking)
  test_errors.py — 8 tests
  test_feedback.py — 13 tests (tmp_path fixture, no filesystem side effects)
```

## Commands

```bash
uv run pytest tests/ -v          # run tests
uv run bitbucket-mcp             # start server (needs env vars)
```

## Auth

Bitbucket Cloud uses **API tokens with scopes** (App Passwords deprecated Sep 2025). Basic Auth with email + scoped token. Token must be created via "Create API token with scopes" > select Bitbucket as app.

Env vars: `BITBUCKET_EMAIL`, `BITBUCKET_API_TOKEN`, `BITBUCKET_WORKSPACE`, `BITBUCKET_FEEDBACK_DIR` (optional, defaults to `~/.bitbucket-mcp/feedback/`)

## Patterns

- Lazy singleton client via `get_client()` in server.py
- Every tool: `try/except BitbucketError` → `e.to_dict()`, generic `Exception` → `{"error": "..."}`
- Client methods return raw API dicts; server tools format them for readability
- `workspace` param optional on every tool (defaults to env var)
- Diff and pipeline logs use `accept` header override to get text instead of JSON
- Tests use `responses` library to mock HTTP, no real API calls
- Meta tools (feedback) use `# ===== META TOOLS =====` section, catch `OSError` instead of `BitbucketError`, don't use BitbucketClient

## Don'ts

- Don't commit `.env` or `.mcp.json` (contain tokens)
- Don't use `BITBUCKET_APP_PASSWORD` — deprecated, use `BITBUCKET_API_TOKEN`
- All code, comments, docstrings, commit messages, and documentation must be in English only
