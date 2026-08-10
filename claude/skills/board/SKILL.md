---
description: Show the Jira sprint board as a TUI kanban. Use when user asks to see the board, sprint, tickets, or kanban view.
user-invocable: true
allowed-tools: Bash, mcp__atlassian__getJiraIssue, Grep, Glob, Read
---

Render the current Jira sprint as a TUI kanban board, or dive into a specific ticket.

**Project**: $ARGUMENTS (default: `JIRA_DEFAULT_PROJECT` from config)

## Configuration

Every site-specific value — cloud id, default project, workflow status names —
lives in a `.env.jira` at the repo root, never in this skill or the script.
`agents-shared/.env.jira.example` documents each field. If `.env.jira` is
missing, the script exits naming the settings it needs; relay that to the user
rather than guessing values.

Read `JIRA_CLOUD_ID` from that file when a step below needs it.

## Parsing arguments

Parse the arguments to extract:
- **Jira URL** (e.g., `https://<site>.atlassian.net/browse/ABC-197`) — extract ticket key `ABC-197`
- **Ticket key** (e.g., `ABC-197`, matches `[A-Z]+-\d+` case-insensitive) — extract project from prefix, pass `-p ABC --key ABC-197`
- **Project key** (bare word without digits, e.g., `ABC`) — `-p` flag only
- `--me` — pass through
- `--assignee "Name"` — pass through
- `--json` — pass through
- Any other flags — pass through

Priority: ticket key/URL detection takes precedence over bare project key extraction.
If neither is found, omit `-p` and let the script fall back to `JIRA_DEFAULT_PROJECT`.

## Locating the board script

The `jira-board.py` script ships with agents-shared. Resolve it through the
global skill symlink:

```bash
SCRIPT="$(dirname "$(readlink "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/board")")/../../scripts/jira-board.py"
```

## Mode A: Specific ticket (URL or ticket key detected)

This is the primary workflow — the user wants to understand and work on a ticket.

### Step 1: Fetch full ticket details

Use the `mcp__atlassian__getJiraIssue` tool:
- `cloudId`: the `JIRA_CLOUD_ID` value from `.env.jira`
- `issueIdOrKey`: the extracted ticket key (e.g., `ABC-4776`)
- `responseContentFormat`: `markdown`

If the Atlassian MCP tool is not available, fall back to the board script with `--key`:

```bash
python3 "$SCRIPT" -p <PROJECT> --key <TICKET_KEY> --json
```

### Step 2: Research the codebase

Based on the ticket description, search the codebase to find relevant files, services, models, and patterns. Use Grep, Glob, and Read as needed.

### Step 3: Present an implementation brief

Render output in this format:

**<KEY>** — <Summary>

| Field | Value |
|-------|-------|
| Status | ... |
| Priority | ... |
| Assignee | ... |
| Parent | ... (if subtask) |

**Description:**
<ticket description, condensed if long>

**Relevant code:**
- `path/to/file.cs:123` — what it does and why it's relevant
- `path/to/other.cs:456` — ...

**Implementation approach:**
<Concrete steps to implement this ticket based on what you found in the codebase. Reference specific files, methods, patterns to follow. Be actionable — the user should be able to start coding from this.>

Do NOT stop after showing the info card. The whole point is to save the user time by bridging the gap between the ticket and the code.

## Mode B: Full board (project key only, or no arguments)

### Running the script

Run with `--json` flag **always** (to get structured data).

```bash
python3 "$SCRIPT" -p <PROJECT> --json [--me] [--assignee "Name"]
```

### Rendering output

**<Project> Sprint Board** (optionally note filter like "my tickets")

| Status | Key | Summary |
|--------|-----|---------|
| In Progress | ABC-1234 | Some task |
| Backlog | ABC-5678 | Another task |

Group rows by status. If there are no issues, say so.

If the user explicitly asks for raw/JSON output, show the JSON instead.
