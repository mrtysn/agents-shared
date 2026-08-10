#!/usr/bin/env python3
"""
TUI Kanban board for Jira — renders the active sprint as a compact board.

Usage:
    ./scripts/jira-board.py              # board for JIRA_DEFAULT_PROJECT
    ./scripts/jira-board.py -p ABC       # a different project
    ./scripts/jira-board.py --json       # raw JSON output

Site-specific settings (cloud id, project, workflow statuses) come from a
.env.jira at your repo root or from the environment — never from this file.
See .env.jira.example for the full list.
"""

import json
import os
import re
import sys
import argparse
import base64
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
#
# Nothing site-specific is baked in here. These are populated at startup from
# .env.jira / the environment; the values below are only fallbacks generic
# enough for a stock Jira workflow.

CLOUD_ID = None                 # required — JIRA_CLOUD_ID
DEFAULT_PROJECT = None          # optional — JIRA_DEFAULT_PROJECT

# Board columns in display order — JIRA_COLUMNS (comma-separated).
COLUMN_ORDER = ["To Do", "In Progress", "In Review"]

# Statuses treated as finished and folded off the board — JIRA_DONE_STATUSES.
DONE_STATUSES = {"Done", "Closed"}

# ANSI
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
PALETTE = ["\033[37m", "\033[36m", "\033[33m", "\033[34m", "\033[32m", "\033[35m"]
COLORS = {}                     # status -> colour, assigned from PALETTE by position


def _assign_colors():
    """Give each configured column a distinct colour, cycling the palette."""
    COLORS.clear()
    for i, col in enumerate(COLUMN_ORDER):
        COLORS[col] = PALETTE[i % len(PALETTE)]

# ── Auth ────────────────────────────────────────────────────────────────────

def _find_env_file():
    """Walk up from cwd to find .env.jira at a repo root."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".env.jira"
        if candidate.exists():
            return candidate
    return None


def _parse_env_file(env_file):
    env = {}
    for line in env_file.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def load_config():
    """Real environment variables win; .env.jira at a repo root fills the rest."""
    env_file = _find_env_file()
    env = _parse_env_file(env_file) if env_file else {}

    def get(key):
        return os.environ.get(key) or env.get(key)

    cfg = {
        "email": get("JIRA_EMAIL"),
        "token": get("JIRA_API_TOKEN"),
        "cloud_id": get("JIRA_CLOUD_ID"),
        "default_project": get("JIRA_DEFAULT_PROJECT"),
        "columns": _split(get("JIRA_COLUMNS")),
        "done_statuses": _split(get("JIRA_DONE_STATUSES")),
    }

    required = {"JIRA_EMAIL": "email", "JIRA_API_TOKEN": "token", "JIRA_CLOUD_ID": "cloud_id"}
    missing = [name for name, key in required.items() if not cfg[key]]
    if missing:
        print(f"ERROR: missing required setting(s): {', '.join(missing)}")
        print("Set them in the environment, or in a .env.jira at your repo root.")
        print("Copy .env.jira.example from agents-shared and fill it in.")
        sys.exit(1)
    return cfg


def _split(value):
    """'a, b ,c' -> ['a','b','c']; None/empty -> None so the default survives."""
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def jira_get(path, email, token):
    url = f"https://api.atlassian.com/ex/jira/{CLOUD_ID}/rest/api/3{path}"
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {creds}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"ERROR: Jira API {e.code}: {body[:200]}")
        sys.exit(1)

# ── Data ────────────────────────────────────────────────────────────────────

def _resolve_my_name(email, token):
    data = jira_get("/myself", email, token)
    return data.get("displayName", "")


def fetch_sprint_issues(project, email, token):
    jql = f"project = {project} AND sprint in openSprints() ORDER BY rank ASC"
    fields = "summary,status,priority,assignee"
    path = f"/search/jql?jql={urllib.parse.quote(jql)}&fields={fields}&maxResults=100"
    data = jira_get(path, email, token)

    issues = []
    for item in data.get("issues", []):
        f = item["fields"]
        issues.append({
            "key": item["key"],
            "summary": f.get("summary", ""),
            "status": f["status"]["name"],
            "priority": f.get("priority", {}).get("name", ""),
            "assignee": (f.get("assignee") or {}).get("displayName", ""),
        })
    return issues


def group_by_status(issues):
    columns = {col: [] for col in COLUMN_ORDER}
    overflow = {}
    for issue in issues:
        status = issue["status"]
        if status in DONE_STATUSES:
            continue
        if status in columns:
            columns[status].append(issue)
        else:
            overflow.setdefault(status, []).append(issue)
    for status, items in overflow.items():
        columns[status] = items
    return columns

# ── Rendering ───────────────────────────────────────────────────────────────

def vlen(s):
    return len(re.sub(r'\033\[[0-9;]*m', '', s))


def wrap_text(text, width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            continue
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines or [""]


def truncate(text, width):
    if len(text) <= width:
        return text
    return text[:width - 1] + "\u2026"


def render_board(columns):
    visible = {k: v for k, v in columns.items() if v}

    if not visible:
        print("No issues in active sprint.")
        return

    try:
        term_w = os.get_terminal_size().columns
    except OSError:
        term_w = 120

    col_count = len(visible)
    sep = " \u2502 "
    sep_w = vlen(sep)
    usable = term_w - sep_w * (col_count - 1)

    # Equal distribution — simple and predictable
    col_w = usable // col_count
    col_widths = {status: col_w for status in visible}

    # Give remainder pixels to the first column
    leftover = usable - col_w * col_count
    if leftover > 0:
        first = next(iter(visible))
        col_widths[first] += leftover

    # Header
    hdrs = []
    for status in visible:
        w = col_widths[status]
        c = COLORS.get(status, "\033[37m")
        count = len(visible[status])
        label = truncate(f"{status.upper()} ({count})", w)
        hdrs.append(f"{c}{BOLD}{label:<{w}}{RST}")
    print()
    print((f"{DIM}{sep}{RST}").join(hdrs))
    print(f"{DIM}{'─' * term_w}{RST}")

    # Rows — each ticket may span multiple lines via word-wrap
    max_rows = max((len(v) for v in visible.values()), default=0)

    for row in range(max_rows):
        # Build wrapped lines for each column's cell
        cells = []
        for status in visible:
            w = col_widths[status]
            items = visible[status]
            if row < len(items):
                issue = items[row]
                key = issue["key"]
                prefix = f"{DIM}{key}{RST} "
                prefix_vlen = len(key) + 1
                text = issue["summary"]
                avail = w - prefix_vlen
                wrapped = wrap_text(text, avail)
                cell_lines = [prefix + wrapped[0]]
                for wl in wrapped[1:]:
                    cell_lines.append(" " * prefix_vlen + wl)
                cells.append(cell_lines)
            else:
                cells.append([""])

        # Pad all cells to same height
        max_lines = max(len(c) for c in cells)
        for ci in range(len(cells)):
            while len(cells[ci]) < max_lines:
                cells[ci].append("")

        # Print line by line
        statuses = list(visible.keys())
        for li in range(max_lines):
            parts = []
            for i, status in enumerate(statuses):
                w = col_widths[status]
                line = cells[i][li]
                pad = w - vlen(line)
                parts.append(line + " " * max(0, pad))
            print((f"{DIM}{sep}{RST}").join(parts))

    print()

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    global CLOUD_ID, DEFAULT_PROJECT, COLUMN_ORDER, DONE_STATUSES

    # Parse args before touching config, so --help works without credentials.
    parser = argparse.ArgumentParser(description="Jira TUI Kanban Board")
    parser.add_argument("--project", "-p",
                        help="Project key (default: JIRA_DEFAULT_PROJECT from .env.jira)")
    parser.add_argument("--me", action="store_true", help="Show only issues assigned to me")
    parser.add_argument("--assignee", "-a", help="Filter by assignee display name (substring match)")
    parser.add_argument("--key", "-k", nargs="+", help="Filter to specific issue key(s)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    cfg = load_config()
    CLOUD_ID = cfg["cloud_id"]
    DEFAULT_PROJECT = cfg["default_project"]
    if cfg["columns"]:
        COLUMN_ORDER = cfg["columns"]
    if cfg["done_statuses"]:
        DONE_STATUSES = set(cfg["done_statuses"])
    _assign_colors()

    project = args.project or DEFAULT_PROJECT
    if not project:
        parser.error("no project key: pass -p PROJECT or set JIRA_DEFAULT_PROJECT in .env.jira")

    email, token = cfg["email"], cfg["token"]
    issues = fetch_sprint_issues(project, email, token)

    if args.key:
        key_set = {k.upper() for k in args.key}
        issues = [i for i in issues if i["key"] in key_set]

    if args.me:
        my_name = _resolve_my_name(email, token)
        issues = [i for i in issues if i["assignee"] == my_name]
    elif args.assignee:
        needle = args.assignee.lower()
        issues = [i for i in issues if needle in i["assignee"].lower()]

    if args.json:
        print(json.dumps(issues, indent=2))
        return

    columns = group_by_status(issues)
    render_board(columns)


if __name__ == "__main__":
    main()
