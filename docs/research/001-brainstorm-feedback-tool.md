# Brainstorm Synthesis: Feedback Tool for Bitbucket MCP Server

**Date:** 2026-02-27
**Agents:** DX Architect (API design, MCP conventions), Pragmatic Engineer (shipping fast, edge cases), Product Thinker (user value, workflow lifecycle)
**Input:** Brainstorming brief — 10 questions across 4 themes

---

## 1. Executive Summary

All three experts agree the feature is low-effort (~50 lines of code) and worth building as a single tool with zero new dependencies. The core disagreement is philosophical: DX Architect and Pragmatic Engineer treat it as an operational utility (write feedback to a stable home directory), while Product Thinker challenges whether local files create enough value versus just adding a prompt instruction to CLAUDE.md or using the Bitbucket Issues API directly. The unanimous recommendation is: ship a ruthlessly minimal MVP (one tool, one file per item, YAML frontmatter) and resist scope creep.

## 2. Consensus (3/3 agree)

### One file per item, not append
All three independently and emphatically chose individual markdown files over a single growing file. Reasons: atomic writes (no locking), easy to grep/delete/resolve individually, simpler implementation (no parsing existing content), compatible with all markdown ecosystems (Obsidian, Hugo, Jekyll).

**Recommended action:** One markdown file per feedback submission. Non-negotiable.

### Minimal parameters: title + description + optional category
All agree on exactly three parameters: `title` (required), `description` (required), `category` (optional string, defaults to `"improvement"` or `"idea"`). All explicitly reject `priority`, `tags`, and `related_tool` for v1.

**Recommended action:** `bb_submit_feedback(title: str, description: str, category: str = "idea")`

### Submit-only for v1 — no list or resolve tools
All three agree: do not build `bb_list_feedback` or `bb_resolve_feedback`. The files are human-readable on disk. The developer can `ls` and `cat` them. Adding companion tools inflates the tool surface (currently 15 tools) for unproven demand.

**Recommended action:** Ship one tool only. Revisit if feedback directory accumulates 20+ items.

### YAML frontmatter format
All three chose YAML frontmatter with 4 core fields: `title`, `category`, `status` (open/resolved), `created`/`date` timestamp. All agree: do NOT use a YAML library to write it — just format as a string.

**Recommended action:** 4-field YAML frontmatter, string-formatted (no PyYAML dependency).

### Timestamp-based filenames with slugified title
All three chose ISO date prefix + slugified title. Matches existing convention in `docs/plans/` (`2026-02-24-bitbucket-mcp-design.md`). All reject UUIDs (opaque) and sequential IDs (require state).

**Recommended action:** `{timestamp}-{slug}.md` with simple regex-based slugify function.

### No automatic context capture
All three agree: capture only the timestamp. MCP tools are stateless — session info and "current tool" are not available at call time. The AI agent will naturally describe context in the description text.

**Recommended action:** Auto-generate timestamp only. Let the caller provide context in description.

### Keep it in this server, not a separate MCP server
All three agree: a separate server for one function is operational overkill (separate process, config, install). The feature is ~50 lines in `server.py`. Put it in a separate section (`# ===== META TOOLS =====` or `# ===== LOCAL TOOLS =====`).

**Recommended action:** Add to `server.py` with a clear section separator.

## 3. Majority (2/3 agree)

### Storage location: home directory vs. repo-local (2 vs 1)

**Majority (DX Architect + Pragmatic Engineer):** Use a stable home directory path (`~/.bitbucket-mcp/feedback/` or `~/.local/share/bitbucket-mcp/feedback/`) with an env var override (`BITBUCKET_FEEDBACK_DIR`). The MCP server runs as an installed package — CWD is unpredictable, and writing relative to it is fragile.

**Dissent (Product Thinker):** Use `./docs/feedback/` (CWD-relative) because that is where the developer already looks. Home directory files are invisible — they will not show up in `git status` and nobody browses `~/.local`. The existing `docs/plans/` convention proves repo-local docs work for this developer.

**Analysis:** Both positions have merit. The home directory is more reliable for a distributed package; repo-local is more discoverable for a solo developer. The env var escape hatch resolves the tension — set it to point at the repo's `docs/feedback/` during development.

### Tool naming: `bb_` prefix or not (2 vs 1)

**Majority (DX Architect + Pragmatic Engineer):** Use `bb_submit_feedback` — consistent with all 15 existing tools, the `bb_` prefix signals "this server's tool."

**Dissent (Product Thinker):** Drop the `bb_` prefix — this tool has nothing to do with Bitbucket. Call it `submit_feedback` to signal the architectural boundary.

**Analysis:** The `bb_` prefix wins for pragmatic consistency. Agents see a flat list of tools; consistent prefixes help tool selection. The section comment provides the architectural boundary for maintainers.

## 4. Disagreements

### Default category value
- DX Architect: `"idea"` — broadest term, no implied commitment
- Pragmatic Engineer: `"improvement"` — most common real-world use
- Product Thinker: `"improvement"` — same reasoning

**Underlying assumption:** "idea" implies brainstorming, "improvement" implies actionability. Both are reasonable. The 2-vs-1 split favors `"improvement"`, but `"idea"` is arguably better for an inbox that is meant to capture rough thoughts before triage.

### CWD fallback behavior
- DX Architect: Never use CWD. Fail if env var is unset and home dir is unavailable.
- Pragmatic Engineer: Never use CWD. Home dir is always available.
- Product Thinker: Fall back to CWD with a warning to stderr.

**Resolution:** Home directory fallback is sufficient. CWD fallback adds complexity for an edge case that the env var already solves.

## 5. Unique Ideas

### DX Architect
- **MCP Resources for feedback:** Expose feedback as `@mcp.resource()` instead of a list tool. Agents browse resources natively without inflating tool count.
- **MCP Prompts for structured collection:** Register an `@mcp.prompt()` that guides the agent through a feedback form before calling the submit tool. Separates gathering from writing.
- **Promote to Bitbucket issue:** `bb_promote_feedback(filename)` reads a feedback file and creates a real Bitbucket issue via the existing API client.

### Pragmatic Engineer
- **JSONL instead of markdown:** Single `feedback.jsonl` file, one JSON line per item. Simpler than one-file-per-item, trivially parseable with `jq`. Near-atomic appends on POSIX.
- **Concrete code skeleton:** Provided a complete ~30-line implementation ready to copy-paste.

### Product Thinker
- **"Do nothing" baseline:** Instead of a tool, add a 5-line instruction to CLAUDE.md: "When you notice improvements, write them to `docs/feedback/`." Claude Code can already write files. Measure the tool against this zero-cost alternative.
- **Challenge the value proposition:** Honest observation that without a team/triage process, feedback files risk becoming a write-only graveyard.

### Shared across 2+ experts
- **Bitbucket Issues API integration** (all 3): The highest-value future evolution — feedback that goes directly to the issue tracker enters an existing workflow. The API client infrastructure already exists.
- **Git commits on a feedback branch** (Pragmatic + Product): Each feedback as a commit on an orphan branch. Versioned, survives `git clean`, reviewed with `git log`.

## 6. Priority Matrix

| Priority | Item | Consensus | Expected Impact | Effort |
|----------|------|-----------|-----------------|--------|
| 1 | One tool: `bb_submit_feedback(title, description, category)` | 3/3 | High | Low |
| 2 | One file per item, YAML frontmatter, timestamp filename | 3/3 | High | Low |
| 3 | Env var `BITBUCKET_FEEDBACK_DIR` for storage path | 3/3 | High | Low |
| 4 | Home directory default (`~/.bitbucket-mcp/feedback/`) | 2/3 | Medium | Low |
| 5 | Tests with `tmp_path` + `monkeypatch.setenv` | 3/3 | Medium | Low |
| 6 | `# ===== META TOOLS =====` section in server.py | 3/3 | Low | Low |
| 7 | `bb_list_feedback` companion tool | 2/3 | Medium | Low |
| 8 | MCP Resource for reading feedback | 1/3 | Medium | Medium |
| 9 | Promote-to-Bitbucket-issue workflow | 3/3 (as future) | High | Medium |
| 10 | MCP Prompt for structured feedback gathering | 1/3 | Low | Medium |

## 7. Recommended Action Sequence

1. **Add `bb_submit_feedback` tool to server.py** — title + description + category params, writes markdown with YAML frontmatter to `BITBUCKET_FEEDBACK_DIR` or `~/.bitbucket-mcp/feedback/`, returns `{success, file, path}`. Catches `OSError` instead of `BitbucketError`. ~50 lines. — Low effort

2. **Add tests in `tests/test_feedback.py`** — Use `tmp_path` fixture + `monkeypatch.setenv("BITBUCKET_FEEDBACK_DIR", ...)`. Test: happy path, dir auto-creation, special chars in title, returned dict structure. ~40 lines. — Low effort

3. **Update CLAUDE.md** — Document the new tool, its purpose, and the `BITBUCKET_FEEDBACK_DIR` env var. — Low effort

4. **Evaluate after real usage** — If 10+ feedback files accumulate, consider `bb_list_feedback` or MCP Resource exposure. If the developer wants feedback in the issue tracker, build the promote-to-Bitbucket-issue workflow (Wild Idea from all 3 experts). — Future, medium effort

5. **Consider the "do nothing" baseline** (Product Thinker's challenge) — Before building, ask: would a 5-line CLAUDE.md instruction achieve 80% of the value? If yes, start there and graduate to a tool only if the prompt approach proves insufficient. — Zero effort
