#!/usr/bin/env python3
"""
recent-sessions: List Claude Code sessions by recency.

Useful for recovering context after a crash or restart. Shows, for each
session: identity, time, size, the first few user prompts, and the most-
touched file. Complements search-history.py (keyword-driven) with a
time-driven view.

Scope: this tool answers "what was I doing recently?". For "find the
session that discussed X", use `/search-history`.

Known limitation: sessions that pivot after opening will be labelled by
their opening prompts. The `top-file` row is an extra discriminator for
those cases, but no cheap heuristic catches every pivot — for deep topic
lookup, reach for search-history.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from claude_dirs import (
    DEFAULT_CONFIG_DIR,
    config_dirs,
    find_transcript,
    live_claude_cwds,
    live_resume_uuids,
)

CACHE_DIR = Path.home() / ".cache" / "search-history"
CACHE_FILE = CACHE_DIR / "last-run.json"
HOME = str(Path.home())

DEFAULT_LIMIT = 25
DEFAULT_DAYS = 3     # 0 = all time
DEFAULT_PROMPTS = 2  # user prompts rendered per session


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
    """Turn `-Users-mert-dev-foo-bar` into `foo-bar` (last path segment).

    Imperfect: dashes inside a real project name collide with the
    path separator, so we keep the last token.
    """
    stripped = dirname.lstrip("-").replace("-", "/")
    return stripped.rsplit("/", 1)[-1] if "/" in stripped else stripped


def contract_home(path: str) -> str:
    if path.startswith(HOME):
        return "~" + path[len(HOME):]
    return path


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


def _session_cwd(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"cwd"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("cwd"):
                    return rec["cwd"]
    except OSError:
        pass
    return None


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
    sid = mapping[key]

    path, config = find_transcript(sid)
    cwd = _session_cwd(path) if path else None

    # refuse to double-resume a session that is already running in another tab
    live = sid in live_resume_uuids() or (
        path and datetime.now().timestamp() - os.path.getmtime(path) < 300
        and cwd in live_claude_cwds()
    )
    if live:
        answer = input(f"Session {sid} appears to be running in another tab. Resume anyway? [y/N] ")
        if answer.strip().lower() != "y":
            sys.exit(1)

    # resume in the session's own cwd and config, so the right project and
    # transcript store are picked up regardless of where this runs from
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)
    if config and config != DEFAULT_CONFIG_DIR:
        os.environ["CLAUDE_CONFIG_DIR"] = config
    os.execvp("claude", ["claude", "--resume", sid])


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


# ─── Session content extraction ──────────────────────────────────────────────

def _extract_user_text(rec: dict) -> str:
    msg = rec.get("message") or {}
    content = msg.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "")
                if t:
                    return t.strip()
    return ""


def extract_session_info(path: Path, want_prompts: int) -> dict:
    """One pass over the jsonl. Returns:
        {
          "prompts":   list[str]  — first N non-command user prompts
          "top_file":  str | None — most-touched file path (by tool_use input.file_path)
        }
    """
    prompts: list[str] = []
    file_counter: Counter[str] = Counter()

    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Quick cheap reject.
                if '"file_path"' not in line and '"type":"user"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # First-few user prompts.
                if len(prompts) < want_prompts and rec.get("type") == "user":
                    text = _extract_user_text(rec)
                    if text and not text.startswith((
                        "<local-command-caveat>",
                        "<command-message>",
                        "<command-name>",
                    )):
                        prompts.append(text)

                # Most-touched file path — pick from any tool_use input containing file_path.
                if rec.get("type") == "assistant":
                    msg = rec.get("message") or {}
                    content = msg.get("content") or []
                    if isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") != "tool_use":
                                continue
                            inp = block.get("input") or {}
                            fp = inp.get("file_path")
                            if isinstance(fp, str) and fp:
                                file_counter[fp] += 1
    except OSError:
        return {"prompts": prompts, "top_file": None}

    top_file = file_counter.most_common(1)[0][0] if file_counter else None
    return {"prompts": prompts, "top_file": top_file}


# ─── Session enumeration ─────────────────────────────────────────────────────

def collect_sessions(
    cutoff: float | None,
    project_filter: str | None,
    current_only: bool,
) -> list[dict]:
    current_dir_name = current_project_dir_name() if current_only else None
    sessions: list[dict] = []

    for config in config_dirs():
        for project_dir in (Path(config) / "projects").iterdir():
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
                    "dirname": project_dir.name,
                    "config": config,
                    "path": str(entry),
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                })

    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


# ─── Rendering ───────────────────────────────────────────────────────────────

def _truncate(text: str, width: int | None) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    if width is None:
        return text
    return text if len(text) <= width else text[: width - 1] + "…"


def render(sessions: list[dict], full: bool) -> None:
    if not sessions:
        print("no sessions matched", file=sys.stderr)
        return

    id_width = 36  # always emit the full UUID; truncation would break copy-paste resume
    proj_width = min(32, max((len(s["project"]) for s in sessions), default=10))
    size_width = 5
    time_width = 11
    live_width = 5
    idx_width = len(str(len(sessions))) + 1  # "#N" style
    header_overhead = idx_width + id_width + proj_width + size_width + time_width + live_width + 12

    if full:
        header_prompt_width: int | None = None
        cont_width: int | None = None
    else:
        try:
            cols = os.get_terminal_size(sys.stdout.fileno()).columns
        except OSError:
            cols = 140
        header_prompt_width = max(20, cols - header_overhead)
        cont_width = max(20, cols - 6)

    indent = "      "

    for i, s in enumerate(sessions, 1):
        prompts = s.get("prompts") or []
        first = prompts[0] if prompts else ""
        sid = s["session_id"]
        proj = s["project"]
        if len(proj) > proj_width:
            proj = proj[: proj_width - 1] + "…"
        idx = f"#{i}"
        print(
            f"{idx:<{idx_width}}  {sid:<{id_width}}  {proj:<{proj_width}}  "
            f"{format_mtime(s['mtime']):<{time_width}}  "
            f"{format_size(s['size']):>{size_width}}  "
            f"{s.get('live') or '':<{live_width}} {_truncate(first, header_prompt_width)}"
        )
        for p in prompts[1:]:
            print(f"{indent}> {_truncate(p, cont_width)}")
        top_file = s.get("top_file")
        if top_file:
            print(f"{indent}~ {_truncate(contract_home(top_file), cont_width)}")

    print(
        f"\n{len(sessions)} session(s). Resume with `recent-sessions --resume N` "
        f"or `claude --resume <full-uuid>`.",
        file=sys.stderr,
    )


# ─── Entry point ─────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="recent-sessions",
        description="List recent Claude Code sessions with their opening prompts and primary file.",
    )
    p.add_argument("--days", "-d", type=int, default=DEFAULT_DAYS,
                   help=f"only sessions from the last N days (default: {DEFAULT_DAYS}, 0=all)")
    p.add_argument("--limit", "-n", type=int, default=DEFAULT_LIMIT,
                   help=f"max sessions to show (default: {DEFAULT_LIMIT}, 0=all)")
    p.add_argument("--project", "-p", help="filter to project (substring match)")
    p.add_argument("--current", "-c", action="store_true",
                   help="filter to current project (from git repo root)")
    p.add_argument("--prompts", type=int, default=DEFAULT_PROMPTS,
                   help=f"number of opening user prompts to show per session (default: {DEFAULT_PROMPTS})")
    p.add_argument("--full", action="store_true",
                   help="do not truncate prompt / file-path columns")
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

    if args.limit and args.limit > 0:
        sessions = sessions[: args.limit]

    # liveness: definite from a --resume argv, probable when the transcript is
    # actively written and a running claude's cwd matches the project
    argv_live = live_resume_uuids()
    live_dirnames = {c.replace("/", "-") for c in live_claude_cwds()}
    now = datetime.now().timestamp()
    for s in sessions:
        if s["session_id"] in argv_live:
            s["live"] = "live"
        elif s["dirname"] in live_dirnames and now - s["mtime"] < 300:
            s["live"] = "live?"
        if s["config"] != DEFAULT_CONFIG_DIR:
            tag = os.path.basename(s["config"]).removeprefix(".claude").lstrip("-") or "?"
            s["project"] += f" [{tag}]"

    want_prompts = max(1, args.prompts)
    for s in sessions:
        info = extract_session_info(Path(s["path"]), want_prompts)
        s["prompts"] = info["prompts"]
        s["top_file"] = info["top_file"]

    save_cache(sessions)
    render(sessions, full=args.full)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
