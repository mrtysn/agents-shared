#!/usr/bin/env python3
# DESC: Search Claude Code session transcripts by keyword across all projects
"""
search-history: Search Claude Code conversation history by keyword.

Searches the user and assistant messages of every session transcript, across
all (or filtered) projects. Regex-capable, with time and project filtering.
The session this runs inside is left out of its results. Searches run against
an index in ~/.cache/search-history, refreshed with whatever the transcripts
gained since the last search.

Modes:
  Default:  session-grouped text output (pipe-friendly)
  --json:   the same results as JSON, for clo's "search history" menu
"""

import argparse
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from claude_dirs import config_dirs

CACHE_DIR = Path.home() / ".cache" / "search-history"
CACHE_FILE = CACHE_DIR / "last-run.json"
DEFAULT_DAYS = 0
DEFAULT_LIMIT = 20
MAX_SNIPPETS_PER_SESSION = 5
MAX_SNIPPETS_JSON = 20
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


def do_resume(number: int):
    """recent-sessions shares the numbered list and owns resuming from it: it
    opens the session in its own folder and config, and refuses a live one."""
    recent = Path(__file__).resolve().parent / "recent-sessions.py"
    os.execv(sys.executable, [sys.executable, str(recent), "--resume", str(number)])


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


def extract_snippet_parts(text: str, match: re.Match, pattern: re.Pattern,
                          context: int = SNIPPET_CONTEXT) -> list[str]:
    """The snippet as [before, match, after], so a viewer can highlight the match.
    The window is cleaned whole and the match found again in it: cleaning the
    halves apart would strand markup like ** around the match."""
    snippet = extract_snippet(text, match, context)
    found = list(pattern.finditer(snippet))
    if not found:
        return [snippet, "", ""]
    # The window may hold the term more than once; take the occurrence that
    # sits where the original match does once the text before it is cleaned.
    start = max(0, match.start() - context)
    lead = len(re.sub(r'\s+', ' ', clean_markup(text[start:match.start()]))) + (start > 0)
    m = min(found, key=lambda f: abs(f.start() - lead))
    return [snippet[:m.start()], m.group(0), snippet[m.end():]]


# Wrappers around text the user pasted or Claude Code injected, not typed.
NOT_TYPED = re.compile(
    r'<(pasted_content|system-reminder|command-message|command-name|command-args|local-command-stdout)\b[^>]*>'
    r'.*?</\1\b[^>]*>',
    re.DOTALL,
)


def typed_prompt(text: str) -> str | None:
    """What the user typed in a prompt, or None for one they did not type:
    a command's transcript caveat, a local command, an interruption notice."""
    if text.startswith(("Caveat:", "<local-command", "[Request interrupted")):
        return None
    text = NOT_TYPED.sub(" ", text)
    text = re.sub(r'\[Image #\d+\]', ' ', text)
    text = re.sub(r'\s+', ' ', clean_markup(text)).strip()
    return text or None


# ─── Index ────────────────────────────────────────────────────────────────────
# The message text of every transcript lives in one SQLite file. Transcripts
# only grow at the end, so each file's read offset is kept and a refresh reads
# only what was appended since: a search costs milliseconds, not a full read.
# Deleting the file is always safe; the next search rebuilds it.

INDEX_FILE = CACHE_DIR / "index.db"
INDEX_VERSION = 1

# A plain term holds none of these; anything else is treated as a regex.
REGEX_CHARS = set("\\.^$*+?{}[]|()")


def open_index() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(INDEX_FILE, timeout=30)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA synchronous = NORMAL")
    if db.execute("PRAGMA user_version").fetchone()[0] != INDEX_VERSION:
        db.executescript(f"""
            DROP TABLE IF EXISTS files;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS messages;
            CREATE TABLE files (path TEXT PRIMARY KEY, session_id TEXT, "offset" INTEGER);
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, project_dir TEXT, cwd TEXT, branch TEXT,
                started TEXT, last TEXT, ai_title TEXT, custom_title TEXT, first_prompt TEXT);
            CREATE VIRTUAL TABLE messages USING fts5(
                text, session_id UNINDEXED, role UNINDEXED, tokenize = 'trigram');
            PRAGMA user_version = {INDEX_VERSION};
        """)
    return db


def forget_file(db: sqlite3.Connection, path: str, session_id: str):
    db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM files WHERE path = ?", (path,))


SESSION_COLUMNS = ("session_id", "project_dir", "cwd", "branch", "started", "last",
                   "ai_title", "custom_title", "first_prompt")


def ingest_file(db: sqlite3.Connection, f: Path):
    """Index what <f> gained since the last refresh, up to its last complete line."""
    path, session_id = str(f), f.stem
    try:
        size = f.stat().st_size
    except OSError:
        return
    row = db.execute('SELECT "offset" FROM files WHERE path = ?', (path,)).fetchone()
    offset = row[0] if row else 0
    if size < offset:  # rewritten, not appended to: start over
        forget_file(db, path, session_id)
        offset = 0
    if size == offset:
        return
    try:
        with open(f, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read(size - offset)
    except OSError:
        return
    end = chunk.rfind(b"\n") + 1  # a line still being written waits for the next refresh
    if end == 0:
        return

    row = db.execute(f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions WHERE session_id = ?",
                     (session_id,)).fetchone()
    s = dict(zip(SESSION_COLUMNS, row)) if row else \
        {**dict.fromkeys(SESSION_COLUMNS), "session_id": session_id, "project_dir": f.parent.name}
    rows = []
    for line in chunk[:end].decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not s["branch"] and entry.get("gitBranch"):
            s["branch"] = entry["gitBranch"]
        if not s["cwd"] and entry.get("cwd"):
            s["cwd"] = entry["cwd"]
        if entry.get("type") == "ai-title" and entry.get("aiTitle"):
            s["ai_title"] = entry["aiTitle"]
        if entry.get("type") == "custom-title" and entry.get("customTitle"):
            s["custom_title"] = entry["customTitle"]
        ts = entry.get("timestamp")
        if ts and (s["started"] is None or ts < s["started"]):
            s["started"] = ts
        if ts and (s["last"] is None or ts > s["last"]):
            s["last"] = ts
        # Skill bodies and other injected text are not part of the conversation.
        if entry.get("isMeta"):
            continue
        text = extract_searchable_text(entry)
        if not text:
            continue
        role = "user" if entry.get("type") == "user" else "asst"
        if s["first_prompt"] is None and role == "user":
            s["first_prompt"] = typed_prompt(text)
        rows.append((text, session_id, role))

    db.executemany("INSERT INTO messages (text, session_id, role) VALUES (?, ?, ?)", rows)
    db.execute(f"INSERT OR REPLACE INTO sessions ({', '.join(SESSION_COLUMNS)}) "
               f"VALUES ({', '.join('?' * len(SESSION_COLUMNS))})", [s[c] for c in SESSION_COLUMNS])
    db.execute('INSERT OR REPLACE INTO files (path, session_id, "offset") VALUES (?, ?, ?)',
               (path, session_id, offset + end))
    # One commit per file: a search killed mid-build keeps what it indexed.
    db.commit()


def refresh_index(db: sqlite3.Connection):
    seen = set()
    for cfg in config_dirs():
        root = Path(cfg) / "projects"
        if not root.is_dir():
            continue
        for f in root.glob("*/*.jsonl"):
            seen.add(str(f))
            ingest_file(db, f)
    for path, session_id in db.execute("SELECT path, session_id FROM files").fetchall():
        if path not in seen:
            forget_file(db, path, session_id)
    db.commit()


# ─── Search engine ────────────────────────────────────────────────────────────

def run_search(
    keyword: str,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    project_filter: str | None = None,
    current_only: bool = False,
    case_sensitive: bool = False,
    max_snippets: int = MAX_SNIPPETS_PER_SESSION,
) -> tuple[list[dict], int, int]:
    """Run search and return (results, n_projects_with_hits, total_found).
    Results rank by how many messages match, discounted by age."""
    plain = not (set(keyword) & REGEX_CHARS)
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(keyword) if plain else keyword, flags)

    db = open_index()
    refresh_index(db)
    db.create_function("regexp", 2, lambda _p, text: pattern.search(text) is not None,
                       deterministic=True)

    # A plain term is a case-insensitive substring, which the trigram index
    # answers; case-sensitivity and regexes go through Python's re.
    if plain:
        like = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        match_sql, match_args = "m.text LIKE ? ESCAPE '\\'", [f"%{like}%"]
        if case_sensitive:
            match_sql += " AND m.text REGEXP ?"
            match_args.append(keyword)
    else:
        match_sql, match_args = "m.text REGEXP ?", [keyword]

    where, args = [match_sql], list(match_args)
    this_session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if this_session:
        where.append("s.session_id != ?")
        args.append(this_session)
    if project_filter:
        where.append("instr(lower(s.project_dir), lower(?)) > 0")
        args.append(project_filter)
    if current_only:
        repo_root = get_repo_root()
        if not repo_root:
            print("Error: --current requires a git repository", file=sys.stderr)
            sys.exit(1)
        where.append("s.project_dir = ?")
        args.append(get_project_dir_for_repo(repo_root))
    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        where.append("s.last >= ?")
        args.append(cutoff)

    hits = db.execute(
        f"SELECT s.*, count(*) FROM messages m JOIN sessions s ON s.session_id = m.session_id "
        f"WHERE {' AND '.join(where)} GROUP BY s.session_id", args).fetchall()

    now = datetime.now(timezone.utc)

    def score(row) -> float:
        last = parse_timestamp(row[5])
        age_days = (now - last).total_seconds() / 86400 if last else 365
        return math.log2(1 + row[-1]) - age_days / 14

    hits.sort(key=score, reverse=True)
    total_found = len(hits)
    if limit > 0:
        hits = hits[:limit]

    results, projects = [], set()
    for row in hits:
        s = dict(zip(SESSION_COLUMNS, row))
        name = os.path.basename(s["cwd"].rstrip("/")) if s["cwd"] else s["project_dir"]
        projects.add(name)
        match_count, snippets = 0, []
        for text, role in db.execute(
                f"SELECT m.text, m.role FROM messages m WHERE m.session_id = ? AND {match_sql} "
                f"ORDER BY m.rowid", [s["session_id"], *match_args]):
            for m in pattern.finditer(text):
                match_count += 1
                if len(snippets) < max_snippets:
                    snippets.append((role, extract_snippet_parts(text, m, pattern)))
        results.append({
            "session_id": s["session_id"],
            "cwd": s["cwd"],
            "project_name": name,
            "branch": s["branch"],
            "started": s["started"],
            "last": s["last"],
            "title": s["custom_title"] or s["ai_title"],
            "preview": s["first_prompt"],
            "match_count": match_count,
            "snippets": snippets,
        })
    db.close()

    if results:
        save_cache(results)
    return results, len(projects), total_found


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
        sid = r["session_id"]
        date = format_timestamp(r["last"])
        project = r["project_name"]
        if len(project) > 16:
            project = project[:15] + "…"
        branch = r["branch"] or "?"
        if len(branch) > 14:
            branch = branch[:13] + "…"
        hits = r["match_count"]
        hit_label = f"{hits} hit" if hits == 1 else f"{hits} hits"

        print(f"  #{i:<{num_w}}  {sid} · {date} · {project} · {branch} · {hit_label}")

        preview = r.get("title") or r.get("preview")
        if preview:
            cleaned = _truncate_preview(preview, 120)
            print(f"{indent}{cleaned}")

        print(f"{indent}─")

        for role, parts in r["snippets"]:
            display = _truncate_word("".join(parts), 200)
            print(f"{indent}[{role}] {display}")

        print()

    print(f"  Resume: search-history --resume N")


def render_json(results: list[dict], keyword: str, n_projects: int, total_found: int):
    keys = ("session_id", "cwd", "project_name", "branch", "started", "last",
            "title", "preview", "match_count")
    out = {
        "keyword": keyword,
        "projects": n_projects,
        "total": total_found,
        "results": [
            {**{k: r[k] for k in keys},
             "preview": _truncate_word(r["preview"], 200) if r["preview"] else None,
             "snippets": [{"role": role, "before": b, "match": m, "after": a}
                          for role, (b, m, a) in r["snippets"]]}
            for r in results
        ],
    }
    json.dump(out, sys.stdout, ensure_ascii=False)
    print()


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
    parser.add_argument("--json", action="store_true",
                        help="Print the results as JSON, with every match's snippet split for highlighting")
    parser.add_argument("--resume", "-r", type=int, default=0,
                        help="Resume session N from the last run (via recent-sessions)")
    args = parser.parse_args()

    if args.resume:
        do_resume(args.resume)
        return

    if not args.keyword:
        parser.error("keyword is required (unless using --resume)")

    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        re.compile(args.keyword, flags)
    except re.error as e:
        print(f"Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    results, n_projects, total_found = run_search(
        keyword=args.keyword,
        days=args.days,
        limit=args.limit,
        project_filter=args.project,
        current_only=args.current,
        case_sensitive=args.case_sensitive,
        max_snippets=MAX_SNIPPETS_JSON if args.json else MAX_SNIPPETS_PER_SESSION,
    )
    if args.json:
        render_json(results, args.keyword, n_projects, total_found)
    else:
        render_output(results, args.keyword, n_projects, total_found)


if __name__ == "__main__":
    main()
