---
description: Show the Jira sprint board as a TUI kanban. Use when user asks to see the board, sprint, tickets, or kanban view.
user-invocable: true
allowed-tools: Bash, mcp__atlassian__getJiraIssue, Grep, Glob, Read
---

Render the current Jira sprint as a TUI kanban board, or dive into a specific ticket.

**Project**: $ARGUMENTS (default: MSB)

## Parsing arguments

Parse the arguments to extract:
- **Jira URL** (e.g., `https://cyphergames.atlassian.net/browse/MSB-197`) — extract ticket key `MSB-197`
- **Ticket key** (e.g., `MSB-197`, matches `[A-Z]+-\d+` case-insensitive) — extract project from prefix, pass `-p MSB --key MSB-197`
- **Project key** (bare word without digits, e.g., `CBD`) — `-p` flag only
- `--me` — pass through
- `--assignee "Name"` — pass through
- `--json` — pass through
- Any other flags — pass through

Priority: ticket key/URL detection takes precedence over bare project key extraction.
If no project key or ticket key is found, default to MSB.

## Locating the board script

The `jira-board.py` script ships with agents-shared. Resolve from the repo root:

```bash
SCRIPT="$(git rev-parse --show-toplevel)/.agents/scripts/jira-board.py"
```

## Mode A: Specific ticket (URL or ticket key detected)

This is the primary workflow — the user wants to understand and work on a ticket.

### Step 1: Fetch full ticket details

Use the `mcp__atlassian__getJiraIssue` tool:
- `cloudId`: `cyphergames.atlassian.net`
- `issueIdOrKey`: the extracted ticket key (e.g., `CBD-4776`)
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
| In Progress | CBD-1234 | Some task |
| Backlog | CBD-5678 | Another task |

Group rows by status. If there are no issues, say so.

If the user explicitly asks for raw/JSON output, show the JSON instead.
