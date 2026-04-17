#!/usr/bin/env python3
"""
blame-session: Find which Claude Code / Codex / Gemini sessions modified the currently changed files.

Scans git status for staged/unstaged changes, then searches local session
transcripts for Edit/Write/Bash tool calls that touched those files. Claude
Code is scanned by default; Codex and Gemini are opt-in via --codex/--gemini
/--all-sources.

Output is file-centric: each changed file lists which sessions touched it.
Sessions are numbered for quick resume via --resume N.

Modes:
  (default)       Static matrix output for terminals and AI agents
  --interactive   Curses TUI with cross-highlighting and enter-to-resume
"""

import argparse
import curses
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

WRITE_TOOLS = {"Edit", "Write", "Bash"}
CACHE_DIR = Path.home() / ".cache" / "blame-session"
CACHE_FILE = CACHE_DIR / "last-run.json"
DEFAULT_DAYS = 14

CODEX_SESSIONS_ROOT = Path.home() / ".codex" / "sessions"
GEMINI_ROOT = Path.home() / ".gemini"
GEMINI_PROJECTS_INDEX = GEMINI_ROOT / "projects.json"

SOURCE_LABELS = {"claude": "Claude", "codex": "Codex", "gemini": "Gemini"}
SOURCE_LABEL_WIDTH = max(len(lbl) for lbl in SOURCE_LABELS.values())
RESUME_COMMANDS = {
    "claude": lambda sid: ["claude", "--resume", sid],
    "codex":  lambda sid: ["codex",  "resume",  sid],
    "gemini": lambda sid: ["gemini", "--resume", sid],
}


# ─── Data gathering ──────────────────────────────────────────────────────────

def get_changed_files(repo_root: str) -> set[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=repo_root
    )
    files = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[1]
        files.add(os.path.normpath(os.path.join(repo_root, path)))
    return files


def get_claude_sessions_for_repo(repo_root: str) -> list[Path]:
    encoded = repo_root.replace("/", "-")
    project_dir = Path.home() / ".claude" / "projects" / encoded
    if not project_dir.exists():
        return []
    return list(project_dir.glob("*.jsonl"))


def get_codex_sessions_for_repo(repo_root: str) -> list[Path]:
    if not CODEX_SESSIONS_ROOT.exists():
        return []
    repo_prefix = repo_root.rstrip("/") + "/"
    matching = []
    for f in CODEX_SESSIONS_ROOT.rglob("rollout-*.jsonl"):
        try:
            with open(f, "r") as fp:
                first = fp.readline()
            if not first.strip():
                continue
            entry = json.loads(first)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if entry.get("type") != "session_meta":
            continue
        cwd = (entry.get("payload") or {}).get("cwd", "")
        if cwd == repo_root or cwd.startswith(repo_prefix):
            matching.append(f)
    return matching


def get_gemini_sessions_for_repo(repo_root: str) -> list[Path]:
    if not GEMINI_PROJECTS_INDEX.exists():
        return []
    try:
        index = json.loads(GEMINI_PROJECTS_INDEX.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    projects = index.get("projects") if isinstance(index, dict) else None
    if not isinstance(projects, dict):
        return []
    slug = projects.get(repo_root)
    if not slug:
        return []
    chats_dir = GEMINI_ROOT / "tmp" / slug / "chats"
    if not chats_dir.exists():
        return []
    return list(chats_dir.glob("session-*.json"))


def extract_file_paths_from_tool(name: str, tool_input: dict) -> list[str]:
    paths = []
    if name in ("Edit", "Write", "Read"):
        fp = tool_input.get("file_path", "")
        if fp:
            paths.append(fp)
    elif name == "Bash":
        cmd = tool_input.get("command", "")
        paths.extend(re.findall(r'(?:>|>>)\s*["\']?(/[^\s"\']+)', cmd))
        paths.extend(re.findall(r'sed\s+-i[^\s]*\s+(?:\'[^\']*\'|"[^"]*")\s+(/[^\s]+)', cmd))
    return [os.path.normpath(p) for p in paths if p.startswith("/")]


def scan_claude_session(session_file: Path, changed_files: set[str], repo_root: str) -> dict | None:
    session_id = session_file.stem
    touched_files = defaultdict(list)
    session_start = None
    session_branch = None
    first_message = None

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

                if not session_branch and entry.get("gitBranch"):
                    session_branch = entry["gitBranch"]

                ts = entry.get("timestamp")
                if ts and (session_start is None or ts < session_start):
                    session_start = ts

                if first_message is None and entry.get("type") == "user":
                    msg_data = entry.get("message", {})
                    content = msg_data.get("content", "")
                    if isinstance(content, str) and content.strip():
                        first_message = content.strip()
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "").strip()
                                if text:
                                    first_message = text
                                    break

                msg = entry.get("message")
                if not msg or entry.get("type") != "assistant":
                    continue

                content = msg.get("content", [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    for fp in extract_file_paths_from_tool(tool_name, tool_input):
                        if fp in changed_files:
                            touched_files[fp].append((tool_name, ts or ""))

    except (OSError, UnicodeDecodeError):
        return None

    if not touched_files:
        return None

    return {
        "source": "claude",
        "session_id": session_id,
        "branch": session_branch,
        "started": session_start,
        "preview": _truncate_preview(first_message) if first_message else None,
        "files": dict(touched_files),
    }


# ─── Codex session scanning ──────────────────────────────────────────────────

def scan_codex_session(session_file: Path, changed_files: set[str], repo_root: str) -> dict | None:
    touched_files = defaultdict(list)
    session_id = None
    session_start = None
    session_branch = None
    first_message = None

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

                etype = entry.get("type")
                payload = entry.get("payload")
                if not isinstance(payload, dict):
                    continue
                ptype = payload.get("type")
                ts = entry.get("timestamp")

                if etype == "session_meta":
                    if not session_id:
                        session_id = payload.get("id")
                    if not session_start:
                        session_start = payload.get("timestamp") or ts
                    if not session_branch:
                        git = payload.get("git")
                        if isinstance(git, dict):
                            session_branch = git.get("branch")
                    continue

                if etype == "event_msg" and ptype == "user_message":
                    if first_message is None:
                        msg = payload.get("message", "")
                        if isinstance(msg, str) and msg.strip():
                            first_message = msg.strip()
                    continue

                if etype == "response_item" and ptype == "function_call":
                    if payload.get("name") != "exec_command":
                        continue
                    args_raw = payload.get("arguments", "")
                    cmd = ""
                    if isinstance(args_raw, str):
                        try:
                            parsed = json.loads(args_raw)
                            if isinstance(parsed, dict):
                                cmd = parsed.get("cmd", "") or ""
                        except json.JSONDecodeError:
                            cmd = ""
                    for fp in extract_file_paths_from_tool("Bash", {"command": cmd}):
                        if fp in changed_files:
                            touched_files[fp].append(("Bash", ts or ""))
                    continue

                if etype == "event_msg" and ptype == "patch_apply_end":
                    if not payload.get("success"):
                        continue
                    changes = payload.get("changes")
                    if not isinstance(changes, dict):
                        continue
                    for path, change in changes.items():
                        if not isinstance(change, dict):
                            continue
                        ctype = change.get("type")
                        tool = "Write" if ctype == "add" else "Edit"
                        for p in (path, change.get("move_path")):
                            if not p:
                                continue
                            norm = os.path.normpath(p)
                            if norm in changed_files:
                                touched_files[norm].append((tool, ts or ""))
                    continue
    except (OSError, UnicodeDecodeError):
        return None

    if not touched_files or not session_id:
        return None

    return {
        "source": "codex",
        "session_id": session_id,
        "branch": session_branch,
        "started": session_start,
        "preview": _truncate_preview(first_message) if first_message else None,
        "files": dict(touched_files),
    }


# ─── Gemini session scanning ─────────────────────────────────────────────────

_GEMINI_TOOL_NAMES = {
    "replace": "Edit",
    "write_file": "Write",
    "run_shell_command": "Bash",
    "read_file": "Read",
}


def scan_gemini_session(session_file: Path, changed_files: set[str], repo_root: str) -> dict | None:
    try:
        with open(session_file, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    session_id = data.get("sessionId")
    session_start = data.get("startTime")
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None

    touched_files = defaultdict(list)
    first_message = None

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        mtype = msg.get("type")
        mts = msg.get("timestamp")

        if first_message is None and mtype == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        if isinstance(text, str) and text.strip():
                            first_message = text.strip()
                            break

        if mtype != "gemini":
            continue

        tool_calls = msg.get("toolCalls")
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            tool = _GEMINI_TOOL_NAMES.get(call.get("name", ""))
            if not tool:
                continue
            args = call.get("args")
            if not isinstance(args, dict):
                continue
            # Gemini stores relative paths and commands; resolve to absolute so
            # the shared extractor (which requires leading '/') matches.
            if tool in ("Edit", "Write", "Read"):
                raw_path = args.get("file_path", "") or ""
                if raw_path and not raw_path.startswith("/"):
                    raw_path = os.path.join(repo_root, raw_path)
                tool_input = {"file_path": raw_path}
            else:  # Bash
                tool_input = {"command": args.get("command", "") or ""}
            for fp in extract_file_paths_from_tool(tool, tool_input):
                if fp in changed_files:
                    touched_files[fp].append((tool, mts or ""))

    if not touched_files or not session_id:
        return None

    return {
        "source": "gemini",
        "session_id": session_id,
        "branch": None,
        "started": session_start,
        "preview": _truncate_preview(first_message) if first_message else None,
        "files": dict(touched_files),
    }


SOURCE_ADAPTERS = {
    "claude": (get_claude_sessions_for_repo, scan_claude_session),
    "codex":  (get_codex_sessions_for_repo,  scan_codex_session),
    "gemini": (get_gemini_sessions_for_repo, scan_gemini_session),
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _truncate_preview(text: str, max_len: int = 60) -> str:
    line = text.split("\n")[0].strip()
    line = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)
    return line[:max_len - 1] + "…" if len(line) > max_len else line


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


def filter_writes_only(result: dict) -> dict | None:
    filtered = {}
    for filepath, actions in result["files"].items():
        write_actions = [(t, ts) for t, ts in actions if t in WRITE_TOOLS]
        if write_actions:
            filtered[filepath] = write_actions
    return {**result, "files": filtered} if filtered else None


def filter_by_days(results: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    filtered = []
    for r in results:
        ts = parse_timestamp(r["started"])
        if ts and ts >= cutoff:
            filtered.append(r)
    return filtered


def save_cache(results: list[dict]):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mapping = {
        str(i): {"source": r.get("source", "claude"), "id": r["session_id"]}
        for i, r in enumerate(results, 1)
    }
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
            print("Run blame-session first to populate the session list.", file=sys.stderr)
        sys.exit(1)
    entry = mapping[key]
    if isinstance(entry, str):
        entry = {"source": "claude", "id": entry}
    source = entry.get("source", "claude")
    sid = entry["id"]
    cmd_fn = RESUME_COMMANDS.get(source, RESUME_COMMANDS["claude"])
    argv = cmd_fn(sid)
    os.execvp(argv[0], argv)


def compute_display_names(rel_paths: list[str]) -> dict[str, str]:
    basenames = Counter(os.path.basename(p) for p in rel_paths)
    display = {}
    for rel in rel_paths:
        base = os.path.basename(rel)
        if basenames[base] == 1:
            display[rel] = base
        else:
            parts = rel.split(os.sep)
            display[rel] = os.path.join(parts[-2], parts[-1]) if len(parts) >= 2 else rel
    seen = Counter(display.values())
    for rel in rel_paths:
        if seen[display[rel]] > 1:
            display[rel] = rel
    return display


def build_file_session_map(results: list[dict], repo_root: str) -> dict[str, list[int]]:
    file_map = defaultdict(list)
    for i, r in enumerate(results, 1):
        for filepath in r["files"]:
            rel = os.path.relpath(filepath, repo_root)
            if i not in file_map[rel]:
                file_map[rel].append(i)
    return dict(file_map)


# ─── Static renderer ─────────────────────────────────────────────────────────

def render_static(results: list[dict], changed_files: set[str], repo_root: str,
                  mode: str, total_found: int):
    n_sessions = len(results)
    num_width = len(str(n_sessions))
    col_width = num_width + 2

    file_map = build_file_session_map(results, repo_root)
    all_matched = set()
    for r in results:
        all_matched.update(r["files"].keys())
    unmatched = sorted(os.path.relpath(f, repo_root) for f in changed_files if f not in all_matched)

    all_files = sorted(file_map.keys()) + unmatched
    display_names = compute_display_names(all_files)
    name_width = min(max((len(d) for d in display_names.values()), default=20), 44)

    # How many columns fit per round
    term_width = shutil.get_terminal_size((120, 24)).columns
    cols_per_round = max((term_width - name_width - 3) // col_width, 3)

    shown_note = f" (showing {n_sessions}/{total_found})" if total_found > n_sessions else ""
    source_counts = Counter(r.get("source", "claude") for r in results)
    source_note = ""
    if len(source_counts) > 1 or "claude" not in source_counts:
        source_note = " · " + ", ".join(
            f"{n} {SOURCE_LABELS.get(s, s)}" for s, n in source_counts.most_common()
        )
    print(f"blame-session · {len(changed_files)} files · {mode}{source_note}{shown_note}")

    # Render matrix in rounds
    for round_start in range(0, n_sessions, cols_per_round):
        round_end = min(round_start + cols_per_round, n_sessions)
        round_indices = list(range(round_start + 1, round_end + 1))  # 1-indexed

        print()

        # Column headers
        header = f" {'':>{name_width}} │"
        for i in round_indices:
            header += f"{i:^{col_width}}"
        print(header)

        sep = f" {'─' * name_width}─┼" + "─" * (col_width * len(round_indices))
        print(sep)

        # File rows
        for rel in sorted(file_map.keys()):
            display = display_names[rel]
            if len(display) > name_width:
                display = display[:name_width - 1] + "…"
            row = f" {display:>{name_width}} │"
            session_set = set(file_map[rel])
            for i in round_indices:
                row += f"{'·':^{col_width}}" if i in session_set else " " * col_width
            print(row)

        for rel in unmatched:
            display = display_names[rel]
            if len(display) > name_width:
                display = display[:name_width - 1] + "…"
            row = f" {display:>{name_width}} │" + " " * (col_width * len(round_indices))
            print(row)

    print()

    # Session legend
    print(f" Sessions")
    print(f" {'─' * 70}")

    multi_source = any(r.get("source", "claude") != "claude" for r in results)

    for i, r in enumerate(results, 1):
        started = format_timestamp(r["started"])
        branch = r["branch"] or "?"
        sid = r["session_id"]
        preview = r.get("preview") or ""
        if preview:
            preview = f"  {preview}"
        label = ""
        if multi_source:
            src = r.get("source", "claude")
            label = f"{SOURCE_LABELS.get(src, src):<{SOURCE_LABEL_WIDTH}}  "
        print(f" {i:>{num_width}}  {label}{sid}  {started:<12}  {branch}{preview}")

    print()
    print(f" Resume: blame-session --resume N")


# ─── Interactive TUI ──────────────────────────────────────────────────────────

def render_interactive(results: list[dict], changed_files: set[str], repo_root: str):
    file_map = build_file_session_map(results, repo_root)
    all_matched = set()
    for r in results:
        all_matched.update(r["files"].keys())
    unmatched = sorted(os.path.relpath(f, repo_root) for f in changed_files if f not in all_matched)

    matched_files = sorted(file_map.keys())
    all_files = matched_files + unmatched
    display_names = compute_display_names(all_files)
    name_width = min(max((len(d) for d in display_names.values()), default=20), 44)

    n_files = len(all_files)
    n_sessions = len(results)

    # Build the boolean matrix: matrix[file_idx][session_idx]
    matrix = []
    for rel in all_files:
        row = set()
        if rel in file_map:
            for s in file_map[rel]:
                row.add(s - 1)  # 0-indexed
        matrix.append(row)

    # Reverse map: for each session, which file indices does it touch
    session_to_files = defaultdict(set)
    for fi, rel in enumerate(all_files):
        for si in matrix[fi]:
            session_to_files[si].add(fi)

    def run_tui(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()

        # Colors
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)     # cursor row/col
        curses.init_pair(2, curses.COLOR_CYAN, -1)                     # highlighted dot
        curses.init_pair(3, curses.COLOR_WHITE, -1)                    # normal dot
        curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_YELLOW)   # active dot (intersection)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)    # dim / unmatched
        curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_GREEN)    # status bar
        curses.init_pair(7, curses.COLOR_YELLOW, -1)                   # header numbers highlighted

        ATTR_CURSOR = curses.color_pair(1) | curses.A_BOLD
        ATTR_HIGHLIGHT = curses.color_pair(2) | curses.A_BOLD
        ATTR_DOT = curses.color_pair(3)
        ATTR_ACTIVE = curses.color_pair(4) | curses.A_BOLD
        ATTR_DIM = curses.color_pair(5)
        ATTR_STATUS = curses.color_pair(6)
        ATTR_HDR_HL = curses.color_pair(7) | curses.A_BOLD

        # Navigation state
        # mode: "file" = navigating file rows, "session" = navigating session columns
        mode = "file"
        cur_file = 0
        cur_session = 0
        scroll_x = 0  # horizontal scroll for session columns
        scroll_y = 0  # vertical scroll for file rows

        num_width = len(str(n_sessions))
        col_width = num_width + 2

        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()

            # Reserve lines: 1 header, 1 col header, 1 separator, file rows, 1 blank, legend, 1 status
            header_y = 0
            col_header_y = 1
            sep_y = 2
            matrix_start_y = 3
            # How many file rows fit
            # Bottom: 1 blank + min(n_sessions, 6) legend + 1 status
            legend_count = min(n_sessions, max(3, max_y // 4))
            bottom_reserve = 1 + legend_count + 1
            matrix_rows = max(max_y - matrix_start_y - bottom_reserve, 1)

            # How many session columns fit
            matrix_cols = max((max_x - name_width - 3) // col_width, 1)

            # Clamp cursor
            cur_file = max(0, min(cur_file, n_files - 1))
            cur_session = max(0, min(cur_session, n_sessions - 1))

            # Auto-scroll to keep cursor visible
            if cur_file < scroll_y:
                scroll_y = cur_file
            elif cur_file >= scroll_y + matrix_rows:
                scroll_y = cur_file - matrix_rows + 1
            if cur_session < scroll_x:
                scroll_x = cur_session
            elif cur_session >= scroll_x + matrix_cols:
                scroll_x = cur_session - matrix_cols + 1

            visible_sessions = list(range(scroll_x, min(scroll_x + matrix_cols, n_sessions)))
            visible_files = list(range(scroll_y, min(scroll_y + matrix_rows, n_files)))

            # Determine which files/sessions to highlight
            if mode == "file":
                hl_sessions = matrix[cur_file]  # sessions touched by current file
                hl_files = {cur_file}
            else:
                hl_files = session_to_files[cur_session]  # files touched by current session
                hl_sessions = {cur_session}

            # ── Header
            title = f"blame-session · {len(changed_files)} files · {n_sessions} sessions"
            source_counts = Counter(r.get("source", "claude") for r in results)
            if len(source_counts) > 1 or "claude" not in source_counts:
                title += " · " + ", ".join(
                    f"{n} {SOURCE_LABELS.get(s, s)}" for s, n in source_counts.most_common()
                )
            if mode == "file" and cur_file < len(all_files):
                title += f"  │  {all_files[cur_file]}"
            elif mode == "session" and cur_session < n_sessions:
                r = results[cur_session]
                label = SOURCE_LABELS.get(r.get("source", "claude"), "?")
                title += f"  │  [{cur_session+1}] {label} {r['session_id']}  {r.get('preview') or ''}"
            _addstr(stdscr, header_y, 0, title[:max_x - 1], curses.A_BOLD)

            # ── Column headers (session numbers)
            _addstr(stdscr, col_header_y, 0, " " * (name_width + 2) + "│", curses.A_DIM)
            for vi, si in enumerate(visible_sessions):
                x = name_width + 3 + vi * col_width
                if x + col_width > max_x:
                    break
                num_str = f"{si + 1:^{col_width}}"
                if si in hl_sessions:
                    attr = ATTR_CURSOR if (mode == "session" and si == cur_session) else ATTR_HDR_HL
                else:
                    attr = curses.A_DIM
                _addstr(stdscr, col_header_y, x, num_str, attr)

            # ── Separator
            sep = " " + "─" * name_width + "─┼" + "─" * (col_width * len(visible_sessions))
            _addstr(stdscr, sep_y, 0, sep[:max_x - 1], curses.A_DIM)

            # ── Matrix rows
            for vi, fi in enumerate(visible_files):
                y = matrix_start_y + vi
                if y >= max_y - bottom_reserve:
                    break

                rel = all_files[fi]
                display = display_names.get(rel, rel)
                if len(display) > name_width:
                    display = display[:name_width - 1] + "…"

                # File name
                is_cur_file = (fi == cur_file and mode == "file")
                is_hl_file = fi in hl_files

                if is_cur_file:
                    name_attr = ATTR_CURSOR
                elif is_hl_file:
                    name_attr = ATTR_HIGHLIGHT
                else:
                    name_attr = curses.A_NORMAL

                _addstr(stdscr, y, 1, f"{display:>{name_width}}", name_attr)
                _addstr(stdscr, y, name_width + 2, "│", curses.A_DIM)

                # Dots
                for vj, si in enumerate(visible_sessions):
                    x = name_width + 3 + vj * col_width
                    if x + col_width > max_x:
                        break

                    has_dot = si in matrix[fi]
                    is_cursor_cross = (fi == cur_file and si == cur_session)
                    si_highlighted = si in hl_sessions
                    fi_highlighted = fi in hl_files

                    if has_dot:
                        if is_cursor_cross:
                            attr = ATTR_ACTIVE
                        elif si_highlighted and fi_highlighted:
                            attr = ATTR_ACTIVE
                        elif si_highlighted or fi_highlighted:
                            attr = ATTR_HIGHLIGHT
                        else:
                            attr = ATTR_DOT
                        _addstr(stdscr, y, x, f"{'●':^{col_width}}", attr)
                    else:
                        if is_cursor_cross:
                            _addstr(stdscr, y, x, f"{'·':^{col_width}}", ATTR_DIM)

            # ── Legend (bottom)
            legend_y = max_y - bottom_reserve + 1
            _addstr(stdscr, legend_y - 1, 0, " Sessions", curses.A_BOLD)

            # Show legend entries centered around current session if in session mode
            if mode == "session":
                legend_center = cur_session
            else:
                # Show most recent
                legend_center = legend_count // 2

            legend_start = max(0, legend_center - legend_count // 2)
            legend_start = min(legend_start, max(0, n_sessions - legend_count))
            legend_end = min(legend_start + legend_count, n_sessions)

            multi_source = any(
                r.get("source", "claude") != "claude" for r in results
            )

            for li, si in enumerate(range(legend_start, legend_end)):
                y = legend_y + li
                if y >= max_y - 1:
                    break

                r = results[si]
                started = format_timestamp(r["started"])
                branch = r["branch"] or "?"
                sid = r["session_id"]
                preview = r.get("preview") or ""
                if preview:
                    preview = f"  {preview}"
                label = ""
                if multi_source:
                    src = r.get("source", "claude")
                    label = f"{SOURCE_LABELS.get(src, src):<{SOURCE_LABEL_WIDTH}}  "
                line = f" {si+1:>{num_width}}  {label}{sid}  {started:<12}  {branch}{preview}"

                if si in hl_sessions:
                    attr = ATTR_CURSOR if (mode == "session" and si == cur_session) else ATTR_HIGHLIGHT
                else:
                    attr = curses.A_DIM

                _addstr(stdscr, y, 0, line[:max_x - 1], attr)

            # ── Status bar
            status_y = max_y - 1
            nav_hint = "↑↓ navigate  Tab switch axis  Enter resume  q quit"
            mode_label = f"  [{mode.upper()}]  "
            status = mode_label + nav_hint
            _addstr(stdscr, status_y, 0, status[:max_x - 1].ljust(max_x - 1), ATTR_STATUS)

            stdscr.refresh()

            # ── Input
            key = stdscr.getch()

            if key == ord('q') or key == 27:  # q or Esc
                break
            elif key == ord('\t') or key == ord('\t'):
                mode = "session" if mode == "file" else "file"
            elif key == curses.KEY_UP or key == ord('k'):
                if mode == "file":
                    cur_file = max(0, cur_file - 1)
                else:
                    cur_session = max(0, cur_session - 1)
            elif key == curses.KEY_DOWN or key == ord('j'):
                if mode == "file":
                    cur_file = min(n_files - 1, cur_file + 1)
                else:
                    cur_session = min(n_sessions - 1, cur_session + 1)
            elif key == curses.KEY_LEFT or key == ord('h'):
                if mode == "session":
                    cur_session = max(0, cur_session - 1)
                else:
                    cur_session = max(0, cur_session - 1)
            elif key == curses.KEY_RIGHT or key == ord('l'):
                if mode == "session":
                    cur_session = min(n_sessions - 1, cur_session + 1)
                else:
                    cur_session = min(n_sessions - 1, cur_session + 1)
            elif key == ord('\n') or key == curses.KEY_ENTER:
                # Resume the current session
                si = cur_session
                if 0 <= si < n_sessions:
                    return results[si]
            elif key == ord('g'):
                cur_file = 0
                cur_session = 0
            elif key == ord('G'):
                if mode == "file":
                    cur_file = n_files - 1
                else:
                    cur_session = n_sessions - 1

        return None

    resumed = curses.wrapper(run_tui)
    if resumed:
        source = resumed.get("source", "claude")
        sid = resumed["session_id"]
        cmd_fn = RESUME_COMMANDS.get(source, RESUME_COMMANDS["claude"])
        argv = cmd_fn(sid)
        os.execvp(argv[0], argv)


def _addstr(stdscr, y: int, x: int, text: str, attr: int = 0):
    """Safe addstr that won't crash on boundary writes."""
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x:
        return
    # Truncate to fit
    available = max_x - x - 1
    if available <= 0:
        return
    try:
        stdscr.addstr(y, x, text[:available], attr)
    except curses.error:
        pass


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Find which Claude/Codex/Gemini sessions modified changed files")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Include sessions that only Read files (default: writes only)")
    parser.add_argument("--limit", "-n", type=int, default=0,
                        help="Max number of sessions to show")
    parser.add_argument("--days", "-d", type=int, default=DEFAULT_DAYS,
                        help=f"Only show sessions from the last N days (default: {DEFAULT_DAYS}, 0=all)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Launch interactive TUI with cross-highlighting")
    parser.add_argument("--resume", "-r", type=int, default=0,
                        help="Resume session by number from last run")
    parser.add_argument("--codex", action="store_true",
                        help="Also scan Codex sessions (~/.codex/sessions)")
    parser.add_argument("--gemini", action="store_true",
                        help="Also scan Gemini sessions (~/.gemini/tmp)")
    parser.add_argument("--all-sources", action="store_true",
                        help="Scan Claude, Codex, and Gemini sessions")
    args = parser.parse_args()

    if args.resume:
        do_resume(args.resume)
        return

    # Force non-interactive if not a TTY
    if args.interactive and not sys.stdout.isatty():
        args.interactive = False

    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: not in a git repository", file=sys.stderr)
        sys.exit(1)
    repo_root = result.stdout.strip()

    changed_files = get_changed_files(repo_root)
    if not changed_files:
        print("No changed files in git status.")
        return

    enabled_sources = ["claude"]
    if args.codex or args.all_sources:
        enabled_sources.append("codex")
    if args.gemini or args.all_sources:
        enabled_sources.append("gemini")

    results = []
    for source in enabled_sources:
        discover, scan = SOURCE_ADAPTERS[source]
        for sf in discover(repo_root):
            hit = scan(sf, changed_files, repo_root)
            if hit:
                if not args.all:
                    hit = filter_writes_only(hit)
                if hit:
                    results.append(hit)

    if not results:
        sources_label = "/".join(SOURCE_LABELS[s] for s in enabled_sources)
        print(f"No {sources_label} sessions found that touched the changed files.")
        if not args.all:
            print("(Try --all to include sessions that only read the files)")
        print(f"\nChanged files ({len(changed_files)}):")
        for f in sorted(changed_files):
            print(f"  {os.path.relpath(f, repo_root)}")
        return

    results.sort(key=lambda r: r["started"] or "", reverse=True)

    # Time-based filter
    if args.days > 0:
        results = filter_by_days(results, args.days)
        if not results:
            print(f"No sessions in the last {args.days} days. Try --days 0 for all time.")
            return

    total_found = len(results)

    if args.limit > 0:
        results = results[:args.limit]

    save_cache(results)

    if args.interactive:
        render_interactive(results, changed_files, repo_root)
    else:
        mode = "all tools" if args.all else "writes only"
        render_static(results, changed_files, repo_root, mode, total_found)


if __name__ == "__main__":
    main()
