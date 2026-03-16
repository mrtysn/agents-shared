#!/usr/bin/env python3
"""
search-history: Search Claude Code conversation history by keyword.

Scans session transcripts across all (or filtered) projects for matching
content in user and assistant messages. Regex-capable, with time and
project filtering.

Output: ranked session list with match counts and snippet previews.
Sessions are numbered for quick resume via --resume N.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path.home() / ".cache" / "search-history"
CACHE_FILE = CACHE_DIR / "last-run.json"
DEFAULT_DAYS = 14
DEFAULT_LIMIT = 20
MAX_SNIPPETS_PER_SESSION = 5
SNIPPET_CONTEXT = 60  # chars on each side of match


# ─── Helpers (shared patterns with blame-session) ────────────────────────────

def format_timestamp(ts_str: str) -> str:
    if not ts_str:
        return "?"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%b %d %H:%M")
    except (ValueError, TypeError):
        return ts_str[:16]


def parse_timestamp(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _truncate_preview(text: str, max_len: int = 60) -> str:
    line = text.split("\n")[0].strip()
    line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
    return line[:max_len - 1] + "…" if len(line) > max_len else line


def save_cache(results: list[dict]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {str(i): r["session_id"] for i, r in enumerate(results, 1)}
    CACHE_FILE.write_text(json.dumps(mapping, indent=2))


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def do_resume(number: int):
    mapping = load_cache()
    key = str(number)
    if key not in mapping:
        print(f"No session [{number}] in last run.", file=sys.stderr)
        if mapping:
            print(f"Valid range: 1-{len(mapping)}", file=sys.stderr)
        else:
            print("Run search-history first to populate the session list.", file=sys.stderr)
        sys.exit(1)
    os.execvp("claude", ["claude", "--resume", mapping[key]])


def get_repo_root() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_project_dir_for_repo(repo_root: str) -> str:
    """Convert repo root to the Claude project directory name."""
    return repo_root.replace("/", "-")


# ─── Content extraction ──────────────────────────────────────────────────────

def extract_searchable_text(entry: dict) -> str | None:
    """Extract searchable text from a user or assistant entry.

    For user entries: string content or text blocks.
    For assistant entries: text blocks only (skip tool_use, tool_result, progress).
    """
    entry_type = entry.get("type")
    if entry_type not in ("user", "assistant"):
        return None

    msg = entry.get("message")
    if not msg:
        return None

    content = msg.get("content", "")

    if isinstance(content, str):
        return content if content.strip() else None

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "\n".join(parts) if parts else None

    return None


def extract_snippet(text: str, match: re.Match, context: int = SNIPPET_CONTEXT) -> str:
    """Extract a snippet around a regex match with context."""
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)

    snippet = text[start:end]
    # Clean up: collapse whitespace, strip newlines
    snippet = re.sub(r'\s+', ' ', snippet).strip()

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{snippet}{suffix}"


# ─── Session scanning ────────────────────────────────────────────────────────

def scan_session(session_file: Path, pattern: re.Pattern) -> dict | None:
    """Scan a session file for keyword matches. Returns match info or None."""
    session_id = session_file.stem
    session_start = None
    session_branch = None
    first_message = None
    matches = []  # list of (role, snippet)
    match_count = 0

    try:
        with open(session_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Track metadata
                if not session_branch and entry.get("gitBranch"):
                    session_branch = entry["gitBranch"]

                ts = entry.get("timestamp")
                if ts and (session_start is None or ts < session_start):
                    session_start = ts

                # Extract first user message for preview
                if first_message is None and entry.get("type") == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.strip():
                        first_message = content.strip()
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    first_message = text
                                    break

                # Search content
                text = extract_searchable_text(entry)
                if not text:
                    continue

                for m in pattern.finditer(text):
                    match_count += 1
                    if len(matches) < MAX_SNIPPETS_PER_SESSION:
                        role = "user" if entry.get("type") == "user" else "asst"
                        matches.append((role, extract_snippet(text, m)))

    except (OSError, UnicodeDecodeError):
        return None

    if match_count == 0:
        return None

    return {
        "session_id": session_id,
        "branch": session_branch,
        "started": session_start,
        "preview": _truncate_preview(first_message) if first_message else None,
        "match_count": match_count,
        "snippets": matches,
    }


# ─── Project discovery ────────────────────────────────────────────────────────

def discover_projects(project_filter: str | None, current_only: bool) -> list[tuple[str, Path]]:
    """Return list of (project_name, project_dir) tuples."""
    if not PROJECTS_DIR.exists():
        return []

    if current_only:
        repo_root = get_repo_root()
        if not repo_root:
            print("Error: --current requires a git repository", file=sys.stderr)
            sys.exit(1)
        encoded = get_project_dir_for_repo(repo_root)
        project_dir = PROJECTS_DIR / encoded
        if project_dir.exists():
            # Derive a short name from the repo root
            name = os.path.basename(repo_root)
            return [(name, project_dir)]
        else:
            print(f"No Claude session directory found for {repo_root}", file=sys.stderr)
            sys.exit(1)

    projects = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        # Derive short name: last path component of the encoded dir
        parts = d.name.split("-")
        # The name is the last meaningful segment (repo name)
        name = parts[-1] if parts else d.name
        # Better: decode the path and take basename
        decoded = d.name.replace("-", "/")
        if decoded.startswith("/"):
            name = os.path.basename(decoded.rstrip("/"))
        else:
            name = d.name

        if project_filter and project_filter.lower() not in d.name.lower():
            continue

        projects.append((name, d))

    return projects


# ─── Rendering ────────────────────────────────────────────────────────────────

def render_output(results: list[dict], keyword: str, n_projects: int, total_found: int):
    n_shown = len(results)
    shown_note = f" (showing {n_shown})" if total_found > n_shown else ""
    print(f'search-history · "{keyword}" · {n_projects} projects · {total_found} matches{shown_note}')
    print()

    if not results:
        print("  No matches found.")
        return

    # Table header
    num_w = len(str(n_shown))
    print(f"  {'#':>{num_w}}  {'Session':<10}  {'Date':<12}  {'Project':<22}  {'Branch':<14}  {'Hits':>4}  Preview")
    print(f"  {'─' * num_w}  {'─' * 10}  {'─' * 12}  {'─' * 22}  {'─' * 14}  {'─' * 4}  {'─' * 30}")

    for i, r in enumerate(results, 1):
        sid = r["session_id"][:8]
        date = format_timestamp(r["started"])
        project = r["project_name"]
        if len(project) > 22:
            project = project[:21] + "…"
        branch = r["branch"] or "?"
        if len(branch) > 14:
            branch = branch[:13] + "…"
        hits = r["match_count"]
        preview = r.get("preview") or ""
        if len(preview) > 30:
            preview = preview[:29] + "…"

        print(f"  {i:>{num_w}}  {sid:<10}  {date:<12}  {project:<22}  {branch:<14}  {hits:>4}  {preview}")

    # Snippets
    print()
    print(f"  Snippets")
    print(f"  {'─' * 72}")

    for i, r in enumerate(results, 1):
        for role, snippet in r["snippets"]:
            # Truncate long snippets
            if len(snippet) > 100:
                snippet = snippet[:99] + "…"
            print(f"  {i:>{num_w}}  [{role}] {snippet}")

    print()
    print(f"  Resume: search-history --resume N")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Search Claude Code conversation history by keyword"
    )
    parser.add_argument("keyword", nargs="?", default=None,
                        help="Search term (regex-capable)")
    parser.add_argument("--days", "-d", type=int, default=DEFAULT_DAYS,
                        help=f"Limit to last N days (default: {DEFAULT_DAYS}, 0=all)")
    parser.add_argument("--limit", "-n", type=int, default=DEFAULT_LIMIT,
                        help=f"Max sessions to show (default: {DEFAULT_LIMIT})")
    parser.add_argument("--project", "-p", type=str, default=None,
                        help="Filter to project (substring match on dir name)")
    parser.add_argument("--current", "-c", action="store_true",
                        help="Filter to current project (from git repo root)")
    parser.add_argument("--case-sensitive", "-s", action="store_true",
                        help="Exact case matching")
    parser.add_argument("--resume", "-r", type=int, default=0,
                        help="Resume session N from last run")
    args = parser.parse_args()

    if args.resume:
        do_resume(args.resume)
        return

    if not args.keyword:
        parser.error("keyword is required (unless using --resume)")

    # Compile pattern
    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        pattern = re.compile(args.keyword, flags)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    # Discover projects
    projects = discover_projects(args.project, args.current)
    if not projects:
        print("No matching projects found.", file=sys.stderr)
        sys.exit(1)

    # Time cutoff for mtime pre-filter
    mtime_cutoff = None
    if args.days > 0:
        mtime_cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp()

    ts_cutoff = None
    if args.days > 0:
        ts_cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # Scan all sessions
    all_results = []
    projects_with_hits = set()

    for project_name, project_dir in projects:
        session_files = list(project_dir.glob("*.jsonl"))

        for sf in session_files:
            # Pre-filter by mtime
            if mtime_cutoff is not None:
                try:
                    if sf.stat().st_mtime < mtime_cutoff:
                        continue
                except OSError:
                    continue

            hit = scan_session(sf, pattern)
            if not hit:
                continue

            # Post-filter by timestamp
            if ts_cutoff:
                ts = parse_timestamp(hit["started"])
                if ts and ts < ts_cutoff:
                    continue

            hit["project_name"] = project_name
            all_results.append(hit)
            projects_with_hits.add(project_name)

    # Sort by start time descending
    all_results.sort(key=lambda r: r["started"] or "", reverse=True)

    total_found = len(all_results)

    # Apply limit
    if args.limit > 0:
        all_results = all_results[:args.limit]

    # Cache for resume
    if all_results:
        save_cache(all_results)

    render_output(all_results, args.keyword, len(projects_with_hits), total_found)


if __name__ == "__main__":
    main()
