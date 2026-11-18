# 073. GitHub MCP server usage (dev workflow, module marketplace, issue reporting)

## What it does
GitHub publishes an official MCP server (`github/github-mcp-server`, MIT). It lets an MCP client such as Claude Code, Claude Desktop, VS Code or Cursor read and write repositories, issues, pull requests, Actions runs, releases and security alerts. It runs either as a hosted remote endpoint (`https://api.githubcopilot.com/mcp/`, OAuth or PAT) or locally via Docker or a binary over stdio. Tools are grouped into toolsets (`context`, `repos`, `issues`, `pull_requests`, `users` by default; `actions`, `code_security`, `dependabot`, `discussions`, `projects` and others on request), and a `--read-only` flag removes every write tool.

This touches the ERP in three places:
1. **Dev workflow:** contributors and module authors triage issues, review PRs and read CI logs from their AI assistant.
2. **Module marketplace:** GitHub Releases could serve as the module registry, so modules do not need a separate registry service.
3. **Issue reporting:** in-app feedback could become structured GitHub issues with diagnostics attached.

## Already in the codebase (with file paths)
- `frontend/src/shared/ui/FeedbackDialog.tsx`: opens a prefilled `issues/new` URL in the browser (title and body only, no diagnostics, no labels or templates).
- `.github/ISSUE_TEMPLATE/bug_report.yml` and `feature_request.yml`, plus `.github/PULL_REQUEST_TEMPLATE.md`. The structured forms exist, but the in-app link does not target them.
- `frontend/src/shared/ui/UpdateChecker.tsx` and `backend/app/main.py` (version check): poll the GitHub Releases API without authentication.
- `backend/app/cli.py`: `openestimate doctor` prints pre-flight checks "before opening a GitHub issue". Its output is not attached to the report.
- `backend/app/core/plugin_manager.py`: `DEFAULT_REGISTRY_URL = https://registry.openestimate.io/api/v1`, `install_from_url()`, `check_updates()` is a `TODO`. `backend/app/core/marketplace.py` is a static catalog.
- There is no MCP config in the repo and no MCP server inside the ERP (topic 065 notes the same).

## Who it helps and how much
- **Small business end users:** low direct value. They do not run GitHub tooling. They benefit indirectly from better bug reports and working module updates.
- **Self-hosting integrators and module authors:** medium value. An agent can scaffold a module, open a PR, read CI failures and draft release notes.
- **Maintainers:** high value for triage. The agent can deduplicate issues with search, apply labels and link to the `doctor` output.
- **Marketplace:** a GitHub-Releases-backed registry would make `check_updates()` implementable with no hosted infrastructure. That fits the "lightweight" principle.

## Implementation effort (Small/Medium/Large, module(s) touched, sketch of how it plugs into the module system)
**Small–Medium overall:**
- **S, docs only:** add a contributor guide snippet showing how to connect the official GitHub MCP server, read-only by default, with the `issues,pull_requests,actions` toolsets. This needs no code.
- **S, frontend plus CLI:** `FeedbackDialog` adds `template=bug_report.yml` and `labels=` to the URL, plus a "copy diagnostics" button fed by a new `GET /api/v1/system/diagnostics` that reuses the `doctor` checks. No token is stored server-side, and the user submits in their own browser.
- **M, `core/plugin_manager.py` and `core/marketplace.py`:** add a `GitHubReleasesRegistry` backend. Each module repo publishes `module.zip` plus a manifest JSON as release assets. `_fetch_module_info()` maps the name to `owner/repo`, reads `releases/latest`, compares the result with the installed `manifest.version` to finish `check_updates()`, and verifies a SHA-256 checksum or signature before `install_from_url()`. An optional token raises the rate limit, which is about 60 requests per hour unauthenticated.
- **Not recommended:** embedding the GitHub MCP server in the ERP runtime. It adds a Go/Docker dependency and credential handling for little end-user value.

## Building blocks (free/open-source libs, APIs, MCP servers — each with a link and license/pricing note)
- **GitHub MCP Server**, official, MIT. Remote hosted or local Docker. Supports read-only mode and toolsets. https://github.com/github/github-mcp-server
- **GitHub REST API for Releases and Issues**: free, with rate limits that are higher when authenticated. https://docs.github.com/en/rest/releases/releases
- **Issue forms via URL query parameters** (`template`, `labels`, `title`, `body`): free. https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue#creating-an-issue-from-a-url-query
- **githubkit** (Python, MIT): typed async client that fits FastAPI and httpx. https://github.com/yanyongyu/githubkit
- **PyGithub** (LGPL-3.0): sync alternative. https://github.com/PyGithub/PyGithub
- **MCP Python SDK** (MIT): only if the ERP later exposes its own MCP server (see topic 065). https://github.com/modelcontextprotocol/python-sdk

I could not verify GA dates or the version numbers that third-party aggregators report. Check GitHub's own README and changelog before relying on them.

## Priority: 2/5 — useful for maintainers and the module ecosystem, but invisible to a small estimating business; the Releases-based update check is the one piece worth building soon.

## Sources
- https://github.com/github/github-mcp-server
- https://github.blog/ai-and-ml/generative-ai/a-practical-guide-on-how-to-use-the-github-mcp-server/
- https://pkg.go.dev/github.com/github/github-mcp-server
- https://docs.github.com/en/rest/releases/releases
- https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-an-issue#creating-an-issue-from-a-url-query
- https://github.com/yanyongyu/githubkit
- https://github.com/modelcontextprotocol/python-sdk
