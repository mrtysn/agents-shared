#!/usr/bin/env python3
"""
search-history: Search Claude Code conversation history by keyword.

Scans session transcripts across all (or filtered) projects for matching
content in user and assistant messages. Regex-capable, with time and
project filtering.

Modes:
  Default:       session-grouped text output (pipe-friendly)
  --interactive:  TUI with browsable session list, expandable snippets, resume
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
DEFAULT_DAYS = 0
DEFAULT_LIMIT = 20
MAX_SNIPPETS_PER_SESSION = 5
SNIPPET_CONTEXT = 100  # chars on each side of match


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


def clean_markup(text: str) -> str:
    """Strip XML/HTML tags, ANSI escapes, and markdown formatting noise."""
    # XML/HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # ANSI escape codes
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    # Markdown bold/italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Code fences
    text = re.sub(r'^```\w*\s*$', '', text, flags=re.MULTILINE)
    # Table separators
    text = re.sub(r'^\s*\|?[\s\-:|]+\|?\s*$', '', text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _truncate_word(text: str, max_len: int) -> str:
    """Truncate text at a word boundary."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    # Try to break at last space
    last_space = cut.rfind(' ')
    if last_space > max_len * 0.6:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def _truncate_preview(text: str, max_len: int = 80) -> str:
    cleaned = clean_markup(text)
    line = cleaned.split("\n")[0].strip()
    return _truncate_word(line, max_len)


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


def do_resume_session_id(session_id: str):
    os.execvp("claude", ["claude", "--resume", session_id])


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
    """Extract searchable text from a user or assistant entry."""
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
    snippet = clean_markup(snippet)
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
    matches = []
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

                if not session_branch and entry.get("gitBranch"):
                    session_branch = entry["gitBranch"]

                ts = entry.get("timestamp")
                if ts and (session_start is None or ts < session_start):
                    session_start = ts

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
        "preview": first_message,
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
            name = os.path.basename(repo_root)
            return [(name, project_dir)]
        else:
            print(f"No Claude session directory found for {repo_root}", file=sys.stderr)
            sys.exit(1)

    projects = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        parts = d.name.split("-")
        name = parts[-1] if parts else d.name
        decoded = d.name.replace("-", "/")
        if decoded.startswith("/"):
            name = os.path.basename(decoded.rstrip("/"))
        else:
            name = d.name

        if project_filter and project_filter.lower() not in d.name.lower():
            continue

        projects.append((name, d))

    return projects


# ─── Search engine ────────────────────────────────────────────────────────────

def run_search(
    keyword: str,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    project_filter: str | None = None,
    current_only: bool = False,
    case_sensitive: bool = False,
) -> tuple[list[dict], int, int]:
    """Run search and return (results, n_projects_with_hits, total_found)."""
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(keyword, flags)

    projects = discover_projects(project_filter, current_only)
    if not projects:
        return [], 0, 0

    mtime_cutoff = None
    if days > 0:
        mtime_cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    ts_cutoff = None
    if days > 0:
        ts_cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    all_results = []
    projects_with_hits = set()

    for project_name, project_dir in projects:
        session_files = list(project_dir.glob("*.jsonl"))

        for sf in session_files:
            if mtime_cutoff is not None:
                try:
                    if sf.stat().st_mtime < mtime_cutoff:
                        continue
                except OSError:
                    continue

            hit = scan_session(sf, pattern)
            if not hit:
                continue

            if ts_cutoff:
                ts = parse_timestamp(hit["started"])
                if ts and ts < ts_cutoff:
                    continue

            hit["project_name"] = project_name
            all_results.append(hit)
            projects_with_hits.add(project_name)

    all_results.sort(key=lambda r: r["started"] or "", reverse=True)
    total_found = len(all_results)

    if limit > 0:
        all_results = all_results[:limit]

    if all_results:
        save_cache(all_results)

    return all_results, len(projects_with_hits), total_found


# ─── Text rendering (non-interactive) ────────────────────────────────────────

def render_output(results: list[dict], keyword: str, n_projects: int, total_found: int):
    n_shown = len(results)
    shown_note = f" (showing {n_shown})" if total_found > n_shown else ""
    print(f'search-history · "{keyword}" · {n_projects} projects · {total_found} matches{shown_note}')
    print()

    if not results:
        print("  No matches found.")
        return

    num_w = len(str(n_shown))
    indent = " " * (num_w + 6)

    for i, r in enumerate(results, 1):
        sid = r["session_id"][:8]
        date = format_timestamp(r["started"])
        project = r["project_name"]
        if len(project) > 16:
            project = project[:15] + "…"
        branch = r["branch"] or "?"
        if len(branch) > 14:
            branch = branch[:13] + "…"
        hits = r["match_count"]
        hit_label = f"{hits} hit" if hits == 1 else f"{hits} hits"

        print(f"  #{i:<{num_w}}  {sid} · {date} · {project} · {branch} · {hit_label}")

        preview = r.get("preview")
        if preview:
            cleaned = _truncate_preview(preview, 120)
            print(f"{indent}{cleaned}")

        print(f"{indent}─")

        for role, snippet in r["snippets"]:
            display = _truncate_word(snippet, 200)
            print(f"{indent}[{role}] {display}")

        print()

    print(f"  Resume: search-history --resume N")


# ─── Interactive TUI ─────────────────────────────────────────────────────────

def run_interactive(search_opts: dict, initial_keyword: str | None = None):
    """Launch the Textual TUI for browsing search results.

    search_opts: dict with keys days, limit, project_filter, current_only, case_sensitive
    initial_keyword: if provided, search runs immediately on launch
    """
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import VerticalScroll
    from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static

    class SessionItem(ListItem):

        def __init__(self, result: dict, index: int) -> None:
            super().__init__()
            self.result = result
            self.index = index

        def compose(self) -> ComposeResult:
            r = self.result
            sid = r["session_id"][:8]
            date = format_timestamp(r["started"])
            project = r["project_name"]
            if len(project) > 16:
                project = project[:15] + "…"
            branch = r["branch"] or "?"
            if len(branch) > 20:
                branch = branch[:19] + "…"
            hits = r["match_count"]
            hit_label = f"{hits} hit" if hits == 1 else f"{hits} hits"

            preview = ""
            if r.get("preview"):
                preview = _truncate_preview(r["preview"], 80)

            yield Static(
                f"[bold]#{self.index}[/bold]  [dim]{sid}[/dim] · {date} · "
                f"[cyan]{project}[/cyan] · [green]{branch}[/green] · {hit_label}\n"
                f"    [dim italic]{preview}[/dim italic]",
                markup=True,
            )

    resume_target = {"session_id": None}

    class SearchHistoryApp(App):
        CSS = """
        Screen {
            background: $surface;
        }
        #search-input {
            dock: top;
            margin: 0 0 1 0;
        }
        #status-bar {
            height: 1;
            background: $primary;
            color: $text;
            padding: 0 1;
        }
        #session-list {
            height: 1fr;
            border: solid $primary;
        }
        #empty-state {
            height: 1fr;
            content-align: center middle;
            color: $text-muted;
        }
        #detail-panel {
            height: auto;
            max-height: 40%;
            border: solid $accent;
            padding: 0 1;
            display: none;
        }
        #detail-panel.visible {
            display: block;
        }
        ListView > ListItem {
            padding: 0 1;
            height: auto;
        }
        ListView > ListItem.--highlight {
            background: $boost;
        }
        #detail-title {
            text-style: bold;
            padding: 0 0 1 0;
        }
        """

        TITLE = "search-history"
        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("ctrl+c", "quit", "Quit", priority=True, show=False),
            Binding("escape", "escape_pressed", "Back", show=False),
            Binding("r", "resume_session", "Resume", priority=True),
            Binding("/", "focus_search", "Search", priority=True),
        ]

        def __init__(self, search_opts: dict, initial_keyword: str | None):
            super().__init__()
            self.search_opts = search_opts
            self.initial_keyword = initial_keyword
            self.results: list[dict] = []
            self.keyword = initial_keyword or ""
            self.n_projects = 0
            self.total_found = 0

        def compose(self) -> ComposeResult:
            yield Header()
            yield Input(
                placeholder="Type a search term and press Enter…",
                value=self.initial_keyword or "",
                id="search-input",
            )
            yield Label("", id="status-bar")
            yield Static(
                "[dim]Type a search term above and press Enter[/dim]",
                id="empty-state",
            )
            yield ListView(id="session-list")
            yield VerticalScroll(
                Static("", id="detail-title"),
                Static("", id="detail-content"),
                id="detail-panel",
            )
            yield Footer()

        def on_mount(self) -> None:
            if self.initial_keyword:
                self._do_search(self.initial_keyword)
            else:
                self.query_one("#session-list").display = False
                self.query_one("#search-input", Input).focus()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            keyword = event.value.strip()
            if keyword:
                self._do_search(keyword)

        def _do_search(self, keyword: str) -> None:
            self.keyword = keyword

            try:
                re.compile(keyword, 0 if self.search_opts.get("case_sensitive") else re.IGNORECASE)
            except re.error:
                self.query_one("#status-bar", Label).update(f" Invalid regex: {keyword}")
                return

            self.results, self.n_projects, self.total_found = run_search(
                keyword=keyword,
                **self.search_opts,
            )

            # Update status
            n_shown = len(self.results)
            shown_note = f" (showing {n_shown})" if self.total_found > n_shown else ""
            self.query_one("#status-bar", Label).update(
                f' "{keyword}" · {self.n_projects} projects · '
                f"{self.total_found} matches{shown_note}"
            )

            # Update list
            lv = self.query_one("#session-list", ListView)
            lv.clear()

            empty = self.query_one("#empty-state", Static)

            if self.results:
                empty.display = False
                lv.display = True
                for i, r in enumerate(self.results, 1):
                    lv.append(SessionItem(r, i))
                lv.focus()
            else:
                lv.display = False
                empty.display = True
                empty.update(f'[dim]No matches for "{keyword}"[/dim]')

            # Close detail panel
            self.query_one("#detail-panel").remove_class("visible")

        def _get_selected_result(self) -> dict | None:
            lv = self.query_one("#session-list", ListView)
            if lv.index is not None and 0 <= lv.index < len(self.results):
                return self.results[lv.index]
            return None

        def action_escape_pressed(self) -> None:
            panel = self.query_one("#detail-panel")
            if panel.has_class("visible"):
                panel.remove_class("visible")
            else:
                self.query_one("#search-input", Input).focus()

        def action_focus_search(self) -> None:
            inp = self.query_one("#search-input", Input)
            inp.focus()
            inp.action_end()

        def action_resume_session(self) -> None:
            # Don't resume if the search input is focused (user is typing 'r')
            if self.query_one("#search-input", Input).has_focus:
                return
            r = self._get_selected_result()
            if r:
                resume_target["session_id"] = r["session_id"]
                self.exit()

        def action_quit(self) -> None:
            self.exit()

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            r = self._get_selected_result()
            if not r:
                return

            panel = self.query_one("#detail-panel")
            title = self.query_one("#detail-title", Static)
            content = self.query_one("#detail-content", Static)

            sid = r["session_id"][:8]
            date = format_timestamp(r["started"])
            project = r["project_name"]
            branch = r["branch"] or "?"
            hits = r["match_count"]

            title.update(
                f"[bold]{sid}[/bold] · {date} · [cyan]{project}[/cyan] · "
                f"[green]{branch}[/green] · {hits} hits"
            )

            lines = []

            if r.get("preview"):
                cleaned = clean_markup(r["preview"])
                preview_lines = cleaned.split("\n")[:5]
                preview_text = "\n".join(ln.strip() for ln in preview_lines if ln.strip())
                lines.append(f"[dim italic]{_truncate_word(preview_text, 500)}[/dim italic]")
                lines.append("─" * 60)

            for role, snippet in r["snippets"]:
                lines.append(f"[yellow]\\[{role}][/yellow] {snippet}")

            lines.append("")
            lines.append("[dim]Press [bold]r[/bold] to resume · [bold]Esc[/bold] to close · [bold]/[/bold] new search[/dim]")

            content.update("\n".join(lines))
            panel.add_class("visible")

    app = SearchHistoryApp(search_opts, initial_keyword)
    app.run()

    if resume_target["session_id"]:
        do_resume_session_id(resume_target["session_id"])


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
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Launch interactive TUI browser")
    parser.add_argument("--resume", "-r", type=int, default=0,
                        help="Resume session N from last run")
    args = parser.parse_args()

    if args.resume:
        do_resume(args.resume)
        return

    # Bare invocation on a TTY drops into the interactive browser.
    # Piped/non-TTY callers (agents, scripts) still get the keyword-required error.
    if not args.keyword and not args.interactive and sys.stdout.isatty():
        args.interactive = True

    search_opts = dict(
        days=args.days,
        limit=args.limit,
        project_filter=args.project,
        current_only=args.current,
        case_sensitive=args.case_sensitive,
    )

    # Interactive mode: keyword is optional (TUI has a search input)
    if args.interactive:
        if args.keyword:
            flags = 0 if args.case_sensitive else re.IGNORECASE
            try:
                re.compile(args.keyword, flags)
            except re.error as e:
                print(f"Invalid regex: {e}", file=sys.stderr)
                sys.exit(1)
        run_interactive(search_opts, initial_keyword=args.keyword)
        return

    # Non-interactive: keyword is required
    if not args.keyword:
        parser.error("keyword is required (unless using --resume or --interactive)")

    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        re.compile(args.keyword, flags)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    results, n_projects, total_found = run_search(keyword=args.keyword, **search_opts)
    render_output(results, args.keyword, n_projects, total_found)


if __name__ == "__main__":
    main()
