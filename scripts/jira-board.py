#!/usr/bin/env python3
"""
TUI Kanban board for Jira — renders the active sprint as a compact board.

Usage:
    ./scripts/jira-board.py              # MSB board (default)
    ./scripts/jira-board.py -p CBD       # different project
    ./scripts/jira-board.py --json       # raw JSON output
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

CLOUD_ID = "e9f3a1e3-ce04-481e-9404-941ca4007666"
DEFAULT_PROJECT = "MSB"

COLUMN_ORDER = ["To Do", "NEXT", "PRIORITY", "In Progress", "RTM", "TEST"]
DONE_STATUSES = {"Done", "Closed", "Parked"}

# ANSI
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
COLORS = {
    "To Do": "\033[37m", "NEXT": "\033[36m", "PRIORITY": "\033[33m",
    "In Progress": "\033[34m", "RTM": "\033[32m", "TEST": "\033[35m",
}

# ── Auth ────────────────────────────────────────────────────────────────────

def load_env():
    repo_root = Path(__file__).resolve().parent.parent
    env_file = repo_root / ".env.jira"
    if not env_file.exists():
        print(f"ERROR: {env_file} not found. Create it with JIRA_EMAIL and JIRA_API_TOKEN.")
        sys.exit(1)

    env = {}
    for line in env_file.read_text().strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()

    email = env.get("JIRA_EMAIL") or os.environ.get("JIRA_EMAIL")
    token = env.get("JIRA_API_TOKEN") or os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        print("ERROR: JIRA_EMAIL and JIRA_API_TOKEN must be set in .env.jira")
        sys.exit(1)
    return email, token


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
    parser = argparse.ArgumentParser(description="Jira TUI Kanban Board")
    parser.add_argument("--project", "-p", default=DEFAULT_PROJECT, help="Project key (default: MSB)")
    parser.add_argument("--me", action="store_true", help="Show only issues assigned to me")
    parser.add_argument("--assignee", "-a", help="Filter by assignee display name (substring match)")
    parser.add_argument("--key", "-k", nargs="+", help="Filter to specific issue key(s)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    email, token = load_env()
    issues = fetch_sprint_issues(args.project, email, token)

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
