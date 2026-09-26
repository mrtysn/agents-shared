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
import tempfile
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
# The message text of every transcript, its subagents' transcripts included,
# lives in one SQLite file, along with the inputs of every tool call (commands,
# file paths, patterns, URLs; never their output). Transcripts only grow at the
# end, so each file's read offset is kept and a refresh reads only what was
# appended since: a search costs milliseconds, not a full read. Deleting the
# file is always safe; the next search rebuilds it.

INDEX_FILE = CACHE_DIR / "index.db"
INDEX_VERSION = 2

# A plain term holds none of these; anything else is treated as a regex.
REGEX_CHARS = set("\\.^$*+?{}[]|()")

# The tool-call inputs worth finding a session by. Edit's old and new strings
# and Write's content are code, and would double the index.
TOOL_FIELDS = ("command", "file_path", "notebook_path", "path", "pattern", "glob",
               "url", "query", "description", "prompt", "skill", "args")


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
            CREATE TABLE files (
                id INTEGER PRIMARY KEY, path TEXT UNIQUE, session_id TEXT,
                subagent INTEGER, "offset" INTEGER);
            CREATE TABLE sessions (
                session_id TEXT PRIMARY KEY, project_dir TEXT, cwd TEXT, branch TEXT,
                started TEXT, last TEXT, ai_title TEXT, custom_title TEXT, first_prompt TEXT);
            -- role: user, asst or tool; "sub-" in front for a subagent's
            CREATE VIRTUAL TABLE messages USING fts5(
                text, session_id UNINDEXED, role UNINDEXED, file UNINDEXED, tokenize = 'trigram');
            PRAGMA user_version = {INDEX_VERSION};
        """)
    return db


def forget_file(db: sqlite3.Connection, file_id: int, session_id: str, subagent: bool):
    db.execute("DELETE FROM messages WHERE file = ?", (file_id,))
    if not subagent:
        db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM files WHERE id = ?", (file_id,))


SESSION_COLUMNS = ("session_id", "project_dir", "cwd", "branch", "started", "last",
                   "ai_title", "custom_title", "first_prompt")


def tool_calls(entry: dict) -> list[str]:
    """Each tool call in an assistant entry, as "<tool>: <inputs>"."""
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    calls = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        inp = block.get("input") or {}
        values = [str(inp[k])[:2000] for k in TOOL_FIELDS
                  if isinstance(inp.get(k), (str, int)) and str(inp[k]).strip()]
        if values:
            calls.append(f"{block.get('name', 'tool')}: " + " · ".join(values))
    return calls


def ingest_file(db: sqlite3.Connection, f: Path, subagent: bool):
    """Index what <f> gained since the last refresh, up to its last complete line.
    A subagent's transcript adds messages to its parent session and nothing else."""
    path = str(f)
    session_id = f.parent.parent.name if subagent else f.stem
    try:
        size = f.stat().st_size
    except OSError:
        return
    row = db.execute('SELECT id, "offset" FROM files WHERE path = ?', (path,)).fetchone()
    file_id, offset = row if row else (None, 0)
    if file_id is not None and size < offset:  # rewritten, not appended to: start over
        forget_file(db, file_id, session_id, subagent)
        file_id, offset = None, 0
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
    if file_id is None:
        file_id = db.execute('INSERT INTO files (path, session_id, subagent, "offset") VALUES (?, ?, ?, 0)',
                             (path, session_id, int(subagent))).lastrowid

    s = None
    if not subagent:
        row = db.execute(f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions WHERE session_id = ?",
                         (session_id,)).fetchone()
        s = dict(zip(SESSION_COLUMNS, row)) if row else \
            {**dict.fromkeys(SESSION_COLUMNS), "session_id": session_id, "project_dir": f.parent.name}
    prefix = "sub-" if subagent else ""
    rows = []
    for line in chunk[:end].decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if s is not None:
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
        for call in tool_calls(entry):
            rows.append((call, session_id, prefix + "tool", file_id))
        text = extract_searchable_text(entry)
        if not text:
            continue
        role = "user" if entry.get("type") == "user" else "asst"
        if s is not None and s["first_prompt"] is None and role == "user":
            s["first_prompt"] = typed_prompt(text)
        rows.append((text, session_id, prefix + role, file_id))

    db.executemany("INSERT INTO messages (text, session_id, role, file) VALUES (?, ?, ?, ?)", rows)
    if s is not None:
        db.execute(f"INSERT OR REPLACE INTO sessions ({', '.join(SESSION_COLUMNS)}) "
                   f"VALUES ({', '.join('?' * len(SESSION_COLUMNS))})", [s[c] for c in SESSION_COLUMNS])
    db.execute('UPDATE files SET "offset" = ? WHERE id = ?', (offset + end, file_id))
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
            ingest_file(db, f, subagent=False)
        for f in root.glob("*/*/subagents/*.jsonl"):
            seen.add(str(f))
            ingest_file(db, f, subagent=True)
    for file_id, path, session_id, subagent in db.execute(
            "SELECT id, path, session_id, subagent FROM files").fetchall():
        if path not in seen:
            forget_file(db, file_id, session_id, bool(subagent))
    db.commit()


# ─── Search engine ────────────────────────────────────────────────────────────

def parse_terms(keyword: str) -> list[str] | None:
    """The words of a plain term, a "quoted phrase" kept whole; None for a regex."""
    if set(keyword) & REGEX_CHARS:
        return None
    return [phrase or word for phrase, word in re.findall(r'"([^"]+)"|(\S+)', keyword)]


def required_literal(regex: str) -> str | None:
    """The longest run of plain text every match of <regex> must contain, so
    the index can narrow the messages before the regex runs; None when that
    cannot be read off safely (alternation or groups, which can make any part
    optional)."""
    if "|" in regex or "(" in regex:
        return None
    runs, run, i = [], "", 0
    while i < len(regex):
        c = regex[i]
        if c == "\\":
            runs.append(run)
            run = ""
            i += 2
            continue
        if c == "[":
            runs.append(run)
            run = ""
            i = regex.find("]", i + 2) + 1 or len(regex)
            continue
        if c in "?*{":
            run = run[:-1]  # the character before is optional or repeated
        if c == "{":
            runs.append(run)
            run = ""
            i = regex.find("}", i) + 1 or len(regex)
            continue
        if c in REGEX_CHARS:
            runs.append(run)
            run = ""
        else:
            run += c
        i += 1
    runs.append(run)
    best = max(runs, key=len)
    return best if len(best) >= 3 else None


def session_filter(project_filter: str | None, current_only: bool, days: int):
    """A predicate over session rows for the --project, --current and --days
    flags. The session this runs inside never passes, nor does one run in a
    temp folder: those are throwaway runs, test harnesses and scratchpads."""
    this_session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    temp_roots = tuple({os.path.realpath(d) + "/" for d in (tempfile.gettempdir(), "/tmp")})
    project_dir = None
    if current_only:
        repo_root = get_repo_root()
        if not repo_root:
            print("Error: --current requires a git repository", file=sys.stderr)
            sys.exit(1)
        project_dir = get_project_dir_for_repo(repo_root)
    cutoff = None
    if days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")

    def keep(s: dict) -> bool:
        return (s["session_id"] != this_session
                and s["cwd"] is not None
                and not (s["cwd"] + "/").startswith(temp_roots)
                and (not project_filter or project_filter.lower() in s["project_dir"].lower())
                and (project_dir is None or s["project_dir"] == project_dir)
                and (cutoff is None or (s["last"] or "") >= cutoff))
    return keep


def result_for(s: dict, match_count: int = 0, snippets: list | None = None,
               title_match: bool = False) -> dict:
    return {
        "session_id": s["session_id"],
        "cwd": s["cwd"],
        "project_name": os.path.basename(s["cwd"].rstrip("/")) or s["cwd"],
        "branch": s["branch"],
        "started": s["started"],
        "last": s["last"],
        "title": s["custom_title"] or s["ai_title"],
        "preview": s["first_prompt"],
        "title_match": title_match,
        "match_count": match_count,
        "snippets": snippets or [],
    }


def load_sessions(db: sqlite3.Connection, keep) -> list[dict]:
    return [s for s in (dict(zip(SESSION_COLUMNS, row)) for row in
                        db.execute(f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions"))
            if keep(s)]


def run_recent(days: int = DEFAULT_DAYS, limit: int = DEFAULT_LIMIT,
               project_filter: str | None = None, current_only: bool = False
               ) -> tuple[list[dict], int, int]:
    """Every session, most recently active first."""
    db = open_index()
    refresh_index(db)
    sessions = load_sessions(db, session_filter(project_filter, current_only, days))
    db.close()
    sessions.sort(key=lambda s: s["last"] or "", reverse=True)
    total = len(sessions)
    results = [result_for(s) for s in (sessions[:limit] if limit > 0 else sessions)]
    if results:
        save_cache(results)
    return results, len({r["project_name"] for r in results}), total


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

    A plain term's words must each appear somewhere in a session: in a message,
    a tool call, the session's title or its first prompt. A regex is one
    pattern. Results rank by how many messages hold the rarest word, well ahead
    when messages hold the words together as typed or the title holds every
    word, discounted by age."""
    flags = 0 if case_sensitive else re.IGNORECASE
    terms = parse_terms(keyword)
    if terms == []:
        return [], 0, 0
    patterns = [re.compile(re.escape(t), flags) for t in terms] if terms else [re.compile(keyword, flags)]
    # The words together as typed, when there are several: the strongest match.
    phrase = re.compile(r"\s+".join(re.escape(t) for t in terms), flags) if terms and len(terms) > 1 else None
    # One pattern for highlighting, the phrase and then the longest words
    # first, so "comic strip" wins over "comic" where both match.
    highlight = re.compile("|".join(([phrase.pattern] if phrase else []) +
                                    [re.escape(t) for t in sorted(terms, key=len, reverse=True)]), flags) \
        if terms else patterns[0]

    db = open_index()
    refresh_index(db)
    regexes = {p.pattern: p for p in patterns + [highlight] + ([phrase] if phrase else [])}
    db.create_function("regexp", 2, lambda p, text: regexes[p].search(text) is not None,
                       deterministic=True)

    # A plain word is a case-insensitive substring, which the trigram index
    # answers; case-sensitivity and regexes go through Python's re.
    def match_sql(p: re.Pattern) -> tuple[str, list]:
        if terms:
            t = terms[patterns.index(p)] if p in patterns else None
            like = t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql, args = "text LIKE ? ESCAPE '\\'", [f"%{like}%"]
            if case_sensitive:
                sql += " AND text REGEXP ?"
                args.append(p.pattern)
            return sql, args
        literal = required_literal(p.pattern)
        if literal:
            like = literal.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            return "text LIKE ? ESCAPE '\\' AND text REGEXP ?", [f"%{like}%", p.pattern]
        return "text REGEXP ?", [p.pattern]

    counts: list[dict[str, int]] = []
    for p in patterns:
        sql, args = match_sql(p)
        counts.append(dict(db.execute(
            f"SELECT session_id, count(*) FROM messages WHERE {sql} GROUP BY session_id", args)))
    phrase_sql, phrase_args = "0 = 1", []
    phrase_counts: dict[str, int] = {}
    if phrase:
        like = " ".join(terms).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        phrase_sql, phrase_args = "text LIKE ? ESCAPE '\\' AND text REGEXP ?", [f"%{like}%", phrase.pattern]
        phrase_counts = dict(db.execute(
            f"SELECT session_id, count(*) FROM messages WHERE {phrase_sql} GROUP BY session_id", phrase_args))

    now = datetime.now(timezone.utc)
    hits = []
    for s in load_sessions(db, session_filter(project_filter, current_only, days)):
        heading = f"{s['custom_title'] or ''} {s['ai_title'] or ''} {s['first_prompt'] or ''}"
        in_heading = [bool(p.search(heading)) for p in patterns]
        if not all(c.get(s["session_id"]) or h for c, h in zip(counts, in_heading)):
            continue
        rarest = min(c.get(s["session_id"], 0) for c in counts)
        together = phrase_counts.get(s["session_id"], 0)
        title_match = all(in_heading)
        last = parse_timestamp(s["last"])
        age_days = (now - last).total_seconds() / 86400 if last else 365
        score = (math.log2(1 + rarest) + 2 * math.log2(1 + together)
                 + (3 if title_match else 0) - age_days / 14)
        hits.append((score, s, title_match))

    hits.sort(key=lambda h: h[0], reverse=True)
    total_found = len(hits)
    if limit > 0:
        hits = hits[:limit]

    clauses = [match_sql(p) for p in patterns]
    any_sql = " OR ".join(f"({sql})" for sql, _ in clauses)
    any_args = [a for _, args in clauses for a in args]
    results = []
    for _, s, title_match in hits:
        match_count, together_count, snippets = 0, 0, []
        for text, role in db.execute(
                f"SELECT text, role FROM messages WHERE session_id = ? AND ({any_sql}) "
                f"ORDER BY ({phrase_sql}) DESC, rowid",
                [s["session_id"], *any_args, *phrase_args]):
            # A message holding the words together shows them together.
            shown = phrase if phrase and phrase.search(text) else highlight
            match_count += sum(1 for _ in highlight.finditer(text))
            if phrase:
                together_count += sum(1 for _ in phrase.finditer(text))
            for m in shown.finditer(text):
                if len(snippets) < max_snippets:
                    snippets.append((role, extract_snippet_parts(text, m, shown)))
        # Where the words appear together, the count is of that: the stronger
        # match, and the one the snippets show.
        results.append(result_for(s, together_count or match_count, snippets, title_match))
    db.close()

    if results:
        save_cache(results)
    return results, len({r["project_name"] for r in results}), total_found


# ─── Text rendering (non-interactive) ────────────────────────────────────────

ROLE_LABELS = {"user": "user", "asst": "asst", "tool": "tool",
               "sub-user": "subagent task", "sub-asst": "subagent", "sub-tool": "subagent tool"}


def render_output(results: list[dict], keyword: str | None, n_projects: int, total_found: int):
    n_shown = len(results)
    shown_note = f" (showing {n_shown})" if total_found > n_shown else ""
    heading = f'"{keyword}"' if keyword else "recent"
    print(f'search-history · {heading} · {n_projects} projects · {total_found} sessions{shown_note}')
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
        hit_label = f" · {hits} hit" if hits == 1 else f" · {hits} hits" if keyword else ""
        if r["title_match"]:
            hit_label += " · in title"

        print(f"  #{i:<{num_w}}  {sid} · {date} · {project} · {branch}{hit_label}")

        preview = r.get("title") or r.get("preview")
        if preview:
            cleaned = _truncate_preview(preview, 120)
            print(f"{indent}{cleaned}")

        if r["snippets"]:
            print(f"{indent}─")
        for role, parts in r["snippets"]:
            display = _truncate_word("".join(parts), 200)
            print(f"{indent}[{ROLE_LABELS.get(role, role)}] {display}")

        print()

    print(f"  Resume: search-history --resume N")


def render_json(results: list[dict], keyword: str | None, n_projects: int, total_found: int):
    keys = ("session_id", "cwd", "project_name", "branch", "started", "last",
            "title", "preview", "title_match", "match_count")
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
                        help='Search term: words that must all appear in a session, "a phrase" in '
                             'quotes; with regex characters, one regex')
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
    parser.add_argument("--recent", action="store_true",
                        help="List sessions by last activity instead of searching")
    parser.add_argument("--resume", "-r", type=int, default=0,
                        help="Resume session N from the last run (via recent-sessions)")
    args = parser.parse_args()

    if args.resume:
        do_resume(args.resume)
        return

    render = render_json if args.json else render_output
    if args.recent:
        results, n_projects, total = run_recent(days=args.days, limit=args.limit,
                                                project_filter=args.project, current_only=args.current)
        render(results, None, n_projects, total)
        return

    if not args.keyword:
        parser.error("keyword is required (unless using --resume or --recent)")

    if parse_terms(args.keyword) is None:
        try:
            re.compile(args.keyword)
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
    render(results, args.keyword, n_projects, total_found)


if __name__ == "__main__":
    main()
