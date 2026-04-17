#!/usr/bin/env python3
"""
recent-sessions: List Claude Code sessions by recency with their first user prompt.

Useful for recovering context after a crash or restart — shows what was
being worked on, when, and in which project. Complements search-history.py
(which is keyword-driven) with a time-driven view.

Modes:
  Default:   table of recent sessions (id, project, mtime, size, first prompt)
  --resume N: resume session number N from the last run (same cache as search-history)
  --match:    filter by keyword in first prompt OR full file content
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path.home() / ".cache" / "search-history"
CACHE_FILE = CACHE_DIR / "last-run.json"

DEFAULT_LIMIT = 25
DEFAULT_DAYS = 3  # 0 = all time


# ─── Helpers ─────────────────────────────────────────────────────────────────

def format_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f}K"
    if n < 1024 ** 3:
        return f"{n / (1024 * 1024):.1f}M"
    return f"{n / (1024 ** 3):.1f}G"


def format_mtime(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%m-%d %H:%M")


def decode_project(dirname: str) -> str:
    """Turn `-Users-mert-dev-foo-bar` into `foo-bar` (last path segment)."""
    stripped = dirname.lstrip("-").replace("-", "/")
    return stripped.rsplit("/", 1)[-1] if "/" in stripped else stripped


def save_cache(sessions: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {str(i): s["session_id"] for i, s in enumerate(sessions, 1)}
    CACHE_FILE.write_text(json.dumps(mapping, indent=2))


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def do_resume(number: int) -> None:
    mapping = load_cache()
    key = str(number)
    if key not in mapping:
        print(f"No session [{number}] in last run.", file=sys.stderr)
        if mapping:
            print(f"Valid range: 1-{len(mapping)}", file=sys.stderr)
        else:
            print("Run recent-sessions (or search-history) first to populate the list.", file=sys.stderr)
        sys.exit(1)
    os.execvp("claude", ["claude", "--resume", mapping[key]])


def get_repo_root() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def current_project_dir_name() -> str | None:
    root = get_repo_root()
    if not root:
        return None
    return root.replace("/", "-")


# ─── First-prompt extraction ─────────────────────────────────────────────────

def extract_first_prompt(path: Path) -> str:
    """Pull the first human user prompt from a session jsonl.

    Skips command-message sidecars and local-command caveats so the result
    reflects what the user actually typed."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"user"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("message") or {}
                content = msg.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                break
                text = (text or "").strip()
                if not text:
                    continue
                if text.startswith(("<local-command-caveat>", "<command-message>", "<command-name>")):
                    continue
                return text
    except OSError:
        return ""
    return ""


# ─── Session enumeration ─────────────────────────────────────────────────────

def collect_sessions(
    cutoff: float | None,
    project_filter: str | None,
    current_only: bool,
) -> list[dict]:
    if not PROJECTS_DIR.exists():
        return []

    current_dir_name = current_project_dir_name() if current_only else None
    sessions: list[dict] = []

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        if current_only:
            if current_dir_name is None or project_dir.name != current_dir_name:
                continue
        label = decode_project(project_dir.name)
        if project_filter and project_filter.lower() not in label.lower():
            continue

        # Top-level .jsonl only — skip subagents/, tool-results/, etc.
        for entry in project_dir.iterdir():
            if not entry.is_file() or entry.suffix != ".jsonl":
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if cutoff is not None and stat.st_mtime < cutoff:
                continue
            sessions.append({
                "session_id": entry.stem,
                "project": label,
                "path": str(entry),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            })

    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


def file_contains(path: Path, pattern: re.Pattern[str]) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if pattern.search(line):
                    return True
    except OSError:
        return False
    return False


# ─── Rendering ───────────────────────────────────────────────────────────────

def render(sessions: list[dict], full: bool, id_len: int) -> None:
    if not sessions:
        print("no sessions matched", file=sys.stderr)
        return

    id_width = max(4, min(36, id_len))
    proj_width = min(32, max((len(s["project"]) for s in sessions), default=10))
    size_width = 5
    time_width = 11
    idx_width = len(str(len(sessions))) + 1  # "#N" style

    if full:
        prompt_width = None
    else:
        try:
            cols = os.get_terminal_size(sys.stdout.fileno()).columns
        except OSError:
            cols = 140
        prompt_width = max(20, cols - idx_width - id_width - proj_width - size_width - time_width - 10)

    for i, s in enumerate(sessions, 1):
        prompt = (s.get("first_prompt") or "").replace("\n", " ").replace("\r", " ")
        if prompt_width is not None and len(prompt) > prompt_width:
            prompt = prompt[: prompt_width - 1] + "…"
        sid = s["session_id"][:id_width]
        proj = s["project"]
        if len(proj) > proj_width:
            proj = proj[: proj_width - 1] + "…"
        idx = f"#{i}"
        print(
            f"{idx:<{idx_width}}  {sid:<{id_width}}  {proj:<{proj_width}}  "
            f"{format_mtime(s['mtime']):<{time_width}}  "
            f"{format_size(s['size']):>{size_width}}  {prompt}"
        )

    print(
        f"\n{len(sessions)} session(s). Resume with `recent-sessions --resume N` "
        f"or `claude --resume <full-uuid>`.",
        file=sys.stderr,
    )


# ─── Entry point ─────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="recent-sessions",
        description="List recent Claude Code sessions with their first user prompt.",
    )
    p.add_argument("--days", "-d", type=int, default=DEFAULT_DAYS,
                   help=f"only sessions from the last N days (default: {DEFAULT_DAYS}, 0=all)")
    p.add_argument("--limit", "-n", type=int, default=DEFAULT_LIMIT,
                   help=f"max sessions to show (default: {DEFAULT_LIMIT}, 0=all)")
    p.add_argument("--project", "-p", help="filter to project (substring match)")
    p.add_argument("--current", "-c", action="store_true",
                   help="filter to current project (from git repo root)")
    p.add_argument("--match", "-m",
                   help="filter to sessions whose first prompt or content matches this regex")
    p.add_argument("--full", action="store_true",
                   help="do not truncate the first-prompt column")
    p.add_argument("--id-len", type=int, default=36,
                   help="session-id characters to show (default: 36, full UUID; lower for preview only)")
    p.add_argument("--resume", "-r", type=int, metavar="N",
                   help="resume session number N from the last run")
    args = p.parse_args(argv)

    if args.resume is not None:
        do_resume(args.resume)
        return 0  # unreachable; execvp replaces process

    cutoff = None
    if args.days and args.days > 0:
        cutoff = (datetime.now() - timedelta(days=args.days)).timestamp()

    sessions = collect_sessions(
        cutoff=cutoff,
        project_filter=args.project,
        current_only=args.current,
    )

    if args.match:
        pattern = re.compile(args.match, re.IGNORECASE)
        filtered = []
        for s in sessions:
            s["first_prompt"] = extract_first_prompt(Path(s["path"]))
            if pattern.search(s["first_prompt"]) or file_contains(Path(s["path"]), pattern):
                filtered.append(s)
        sessions = filtered
    else:
        load_limit = args.limit if args.limit > 0 else len(sessions)
        for s in sessions[:load_limit]:
            s["first_prompt"] = extract_first_prompt(Path(s["path"]))

    if args.limit and args.limit > 0:
        sessions = sessions[: args.limit]

    save_cache(sessions)
    render(sessions, full=args.full, id_len=args.id_len)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
