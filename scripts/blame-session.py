#!/usr/bin/env python3
"""
blame-session: Find which Claude Code sessions modified the currently changed files.

Scans git status for staged/unstaged changes, then searches Claude Code session
transcripts for Edit/Write/Bash tool calls that touched those files.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WRITE_TOOLS = {"Edit", "Write", "Bash"}


def get_changed_files(repo_root: str) -> set[str]:
    """Get all staged and unstaged changed files from git status."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=repo_root
    )
    files = set()
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        # porcelain format: XY filename
        # or XY orig -> renamed
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[1]
        # Resolve to absolute path
        abs_path = os.path.normpath(os.path.join(repo_root, path))
        files.add(abs_path)
    return files


def get_claude_project_dir(repo_root: str) -> Path | None:
    """Derive the Claude project directory path from the repo root."""
    # Claude stores sessions under ~/.claude/projects/<encoded-path>/
    # where <encoded-path> is the absolute path with / replaced by -
    encoded = repo_root.replace("/", "-")
    project_dir = Path.home() / ".claude" / "projects" / encoded
    if project_dir.exists():
        return project_dir
    return None


def extract_file_paths_from_tool(name: str, tool_input: dict) -> list[str]:
    """Extract file paths from a tool call's input."""
    paths = []

    if name in ("Edit", "Write", "Read"):
        fp = tool_input.get("file_path", "")
        if fp:
            paths.append(fp)

    elif name == "Bash":
        cmd = tool_input.get("command", "")
        # Look for obvious file write patterns in bash commands
        # This is heuristic - catches sed -i, redirects mentioned with known paths, etc.
        # We'll match against changed files later, so false positives are filtered out
        paths.extend(re.findall(r'(?:>|>>)\s*["\']?(/[^\s"\']+)', cmd))
        # sed -i
        sed_match = re.findall(r'sed\s+-i[^\s]*\s+(?:\'[^\']*\'|"[^"]*")\s+(/[^\s]+)', cmd)
        paths.extend(sed_match)

    return [os.path.normpath(p) for p in paths if p.startswith("/")]


def scan_session(session_file: Path, changed_files: set[str]) -> dict | None:
    """Scan a single session file for tool calls that touched changed files."""
    session_id = session_file.stem
    touched_files = defaultdict(list)  # file -> list of (tool_name, timestamp)
    session_start = None
    session_branch = None
    session_slug = None

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

                # Capture session metadata
                if not session_branch and entry.get("gitBranch"):
                    session_branch = entry["gitBranch"]
                if not session_slug and entry.get("slug"):
                    session_slug = entry["slug"]

                # Track earliest timestamp
                ts = entry.get("timestamp")
                if ts and (session_start is None or ts < session_start):
                    session_start = ts

                # Look for assistant tool_use messages
                msg = entry.get("message")
                if not msg or entry.get("type") != "assistant":
                    continue

                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "tool_use":
                        continue

                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})

                    file_paths = extract_file_paths_from_tool(tool_name, tool_input)
                    for fp in file_paths:
                        if fp in changed_files:
                            touched_files[fp].append((tool_name, ts or ""))

    except (OSError, UnicodeDecodeError):
        return None

    if not touched_files:
        return None

    return {
        "session_id": session_id,
        "branch": session_branch,
        "slug": session_slug,
        "started": session_start,
        "files": dict(touched_files),
    }


def format_timestamp(ts_str: str) -> str:
    """Format ISO timestamp to a readable local time."""
    if not ts_str:
        return "?"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ts_str[:16]


def filter_writes_only(result: dict) -> dict | None:
    """Filter a session result to only include files that had write tool calls."""
    filtered_files = {}
    for filepath, actions in result["files"].items():
        write_actions = [(t, ts) for t, ts in actions if t in WRITE_TOOLS]
        if write_actions:
            filtered_files[filepath] = write_actions
    if not filtered_files:
        return None
    return {**result, "files": filtered_files}


def main():
    parser = argparse.ArgumentParser(description="Find which Claude sessions modified changed files")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Include sessions that only Read files (default: writes only)")
    parser.add_argument("--limit", "-n", type=int, default=0,
                        help="Max number of sessions to show (default: all)")
    args = parser.parse_args()

    # Determine repo root
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: not in a git repository", file=sys.stderr)
        sys.exit(1)
    repo_root = result.stdout.strip()

    # Get changed files
    changed_files = get_changed_files(repo_root)
    if not changed_files:
        print("No changed files in git status.")
        return

    # Find Claude project dir
    project_dir = get_claude_project_dir(repo_root)
    if not project_dir:
        print(f"No Claude session directory found for {repo_root}", file=sys.stderr)
        sys.exit(1)

    # Scan all session files
    session_files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)

    results = []
    for sf in session_files:
        hit = scan_session(sf, changed_files)
        if hit:
            if not args.all:
                hit = filter_writes_only(hit)
            if hit:
                results.append(hit)

    if not results:
        print("No Claude sessions found that touched the changed files.")
        if not args.all:
            print("(Try --all to include sessions that only read the files)")
        print(f"\nChanged files ({len(changed_files)}):")
        for f in sorted(changed_files):
            rel = os.path.relpath(f, repo_root)
            print(f"  {rel}")
        return

    # Sort by most recent first
    results.sort(key=lambda r: r["started"] or "", reverse=True)

    if args.limit > 0:
        results = results[:args.limit]

    # Output
    mode = "all tool calls" if args.all else "writes only"
    print(f"Changed files: {len(changed_files)}  |  Mode: {mode}")
    print(f"Sessions found: {len(results)}")
    print()

    for r in results:
        started = format_timestamp(r["started"])
        branch = r["branch"] or "?"
        slug = r["slug"] or ""
        sid = r["session_id"]

        print(f"{'─' * 70}")
        slug_display = f"  ({slug})" if slug else ""
        print(f"Session: {sid}{slug_display}")
        print(f"Branch:  {branch}  |  Started: {started}")
        print(f"Resume:  claude --resume {sid}")
        print()

        for filepath, actions in sorted(r["files"].items()):
            rel = os.path.relpath(filepath, repo_root)
            # Deduplicate tool names
            tools = sorted(set(a[0] for a in actions))
            count = len(actions)
            print(f"  {rel}")
            print(f"    {', '.join(tools)} ({count} call{'s' if count > 1 else ''})")
        print()


if __name__ == "__main__":
    main()
