#!/usr/bin/env python3
# DESC: Read Claude Code transcripts as ordered text or JSON rows: one session or all, with tool calls and the user's next message
"""
extract-session-text: Turn Claude Code transcripts (.jsonl) into ordered plain
text, or into JSON rows, so a session can be read in chunks or many sessions
mined. This is the one way to read transcripts: do not write a jsonl parser.
Transcript parsing lives in transcript_items.py, which this script and the
find-* surveys share.

One session: pass a transcript path or a session id; an id is resolved by
searching ${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/<id>.jsonl (then every
other config dir claude_dirs.py knows). Many sessions: --all, narrowed by
--project, --days, --since/--until and --session-mentions. Kinds:

  user       typed messages, queued messages, compaction summaries, recaps
  assistant  the assistant's text blocks
  agents     sub-agent spawn prompts, SendMessage calls, questions asked of
             the user (AskUserQuestion: an ASK row with the questions and options as JSON,
             then a RESULT AskUserQuestion row with the user's choice, typed answer or
             rejection) and the hand-back results that answer them. These rows are in
             agents, not calls or tools: --kinds calls,tools,user never shows a question
  calls      every other tool call: its command, path or pattern (input in JSON)
  tools      every other tool result (off by default; can be huge)
  attachments  the rule text a path match loaded (RULE-LOADED <file>) and the context a
             hook added (HOOK-CONTEXT <hook>); off by default. Use it to see whether a
             rule or hook note reached a session, and where, instead of grepping the file.

Sidechain (sub-agent internal) entries are left out unless --subagents.

--json prints one JSON object per line instead of text. A row has: session,
project, time, cwd, group, label, text, sidechain, meta, origin, api_error, and
on tool rows tool, tool_use_id and input. --next-user adds next_user to every
row: the next typed prompt later in that session (null at the end). Tool inputs
and results are cut to --max-chars characters in --json (default 2000, 0 = no
cut); user, assistant and agents text is never cut.

Examples:
  extract-session-text.py edb80266-8503-443e-8398-d29d6002e446 --out session.txt
  extract-session-text.py session.jsonl --kinds user,agents --chunk-chars 60000 --out /tmp/s/chunk
  extract-session-text.py session.jsonl --grep 'rebuild' --since 2026-09-20
  extract-session-text.py session.jsonl --kinds assistant,agents --since-last-user --json
  extract-session-text.py <session-id> --kinds user,assistant --around 2026-10-13T06:25 --context 6
  extract-session-text.py --all --days 14 --project asset-pipeline --kinds assistant,calls --json --next-user
  extract-session-text.py --all --window
  extract-session-text.py --all --days 30 --session-mentions '"skill": ?"archify"' --kinds user --grep 'depth'
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_dirs import find_transcript  # noqa: E402
from transcript_items import add_next_user, clip_input, items, since_last_user, transcripts  # noqa: E402

KINDS = ("user", "assistant", "agents", "calls", "tools", "attachments")
UUID_ONLY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
JSON_MAX_CHARS = 2000


def resolve(arg):
    p = Path(arg).expanduser()
    if p.is_file():
        return p
    if UUID_ONLY.match(arg):
        cfg = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
        for m in sorted(Path(cfg).glob(f"projects/*/{arg}.jsonl")):
            return m
        found, _ = find_transcript(arg)
        if found:
            return Path(found)
    sys.exit(f"extract-session-text: no transcript for '{arg}'")


def is_noise(label, text):
    if label == "META" and text.startswith("Another Claude session"):
        return True
    if "task-notification" in text and "delivered to you as a message" in text:
        return True
    if label.startswith("RESULT") and "Async agent launched" in text:
        return True
    return False


def session_rows(path, project, session, want, a):
    """One session's kept rows, in order."""
    build = None if a.next_user else want | {"user"}
    if a.since_last_user and build is not None:
        build = build | {"agents"}  # the boundary is a typed prompt or an AskUserQuestion answer
    rows = list(items(str(path), project, session, build))
    if a.next_user:
        add_next_user(rows)
    if a.since_last_user:
        rows = since_last_user(rows)
    return [r for r in rows if r["group"] in want and (a.subagents or not r["sidechain"])
            and not is_noise(r["label"], r["text"])]


FIRST_TIME = re.compile(r'"timestamp":\s*"([^"]+)"')


def print_window(sources):
    count, earliest, latest = 0, None, 0.0
    for path, _, _ in sources:
        count += 1
        latest = max(latest, os.path.getmtime(path))
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                m = FIRST_TIME.search(raw)
                if m:
                    earliest = min(earliest or m.group(1), m.group(1))
                    break
    last = datetime.datetime.fromtimestamp(latest, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M") if count else "-"
    print(f"{count} sessions; earliest entry {earliest or '-'}; latest modified {last} (UTC)")


def main():
    ap = argparse.ArgumentParser(
        description="Read Claude Code transcripts as ordered plain text or JSON rows.",
        epilog="example: extract-session-text.py <session-id> --kinds user,assistant --chunk-chars 60000 --out /tmp/s/chunk",
    )
    ap.add_argument("session", nargs="?", help="transcript .jsonl path, or a session id (omit with --all)")
    ap.add_argument("--all", action="store_true", help="read every session under every Claude config dir")
    ap.add_argument("--project", metavar="TEXT", help="with --all: only projects whose folder name contains TEXT")
    ap.add_argument("--days", type=int, metavar="N", help="with --all: only sessions touched in the last N days, and entries from those days")
    ap.add_argument("--session-mentions", metavar="REGEX",
                    help="with --all: only sessions whose raw transcript contains REGEX anywhere, skill listings included; "
                         "use a pattern that only a real use produces, e.g. '\"skill\": ?\"archify\"'")
    ap.add_argument("--exclude-session", action="append", default=[], metavar="ID", help="with --all: leave out a session (id prefix; repeatable)")
    ap.add_argument("--window", action="store_true",
                    help="with --all: print how many sessions match and the earliest and latest time they cover, then stop "
                         "(the edge to state in any report: nothing earlier is visible)")
    ap.add_argument("--subagents", action="store_true", help="include sub-agent transcripts (their rows have sidechain true)")
    ap.add_argument("--kinds", default="user,assistant,agents",
                    help=f"comma list of {','.join(KINDS)} (default: user,assistant,agents)")
    ap.add_argument("--json", action="store_true", help="print JSON rows, one per line, instead of text")
    ap.add_argument("--next-user", action="store_true", help="with --json: add next_user, the next typed prompt in the session")
    ap.add_argument("--max-chars", type=int, metavar="N",
                    help=f"cut tool calls, tool results and tool inputs to N characters (default {JSON_MAX_CHARS} with --json, no cut in text; 0 = no cut)")
    ap.add_argument("--out", help="output file; stdout if omitted. With --chunk-chars, a prefix for <out>-001.txt, ...")
    ap.add_argument("--chunk-chars", type=int, metavar="N",
                    help="write numbered chunk files of about N characters (needs --out); entries are never split")
    ap.add_argument("--since-last-user", action="store_true",
                    help="keep only the rows after the last user reply: a typed prompt, or the answer to an "
                         "AskUserQuestion call. What the assistant has done since the user last spoke; a hook "
                         "given a transcript path uses it to check the current turn")
    ap.add_argument("--since", metavar="YYYY-MM-DD[THH:MM]", help="keep entries at or after this UTC timestamp")
    ap.add_argument("--until", metavar="YYYY-MM-DD[THH:MM]", help="keep entries before this UTC timestamp")
    ap.add_argument("--grep", metavar="REGEX", help="keep entries whose text matches (case-insensitive)")
    ap.add_argument("--around", metavar="YYYY-MM-DDTHH:MM[:SS]",
                    help="keep only the entries near this UTC timestamp: --context N before and after the first entry at or after it")
    ap.add_argument("--context", type=int, default=6, metavar="N", help="entries kept each side of --around (default 6)")
    a = ap.parse_args()

    want = {k.strip() for k in a.kinds.split(",") if k.strip()}
    bad = want - set(KINDS)
    if bad or not want:
        ap.error(f"--kinds takes {', '.join(KINDS)}")
    if a.chunk_chars and not a.out:
        ap.error("--chunk-chars needs --out")
    if a.chunk_chars and a.json:
        ap.error("--chunk-chars writes text; drop --json")
    if a.next_user and not a.json:
        ap.error("--next-user needs --json")
    if bool(a.session) == a.all:
        ap.error("give a session, or --all")
    if a.window and not a.all:
        ap.error("--window needs --all")
    if a.around and a.all:
        ap.error("--around reads one session")
    if a.since_last_user and a.all:
        ap.error("--since-last-user reads one session")
    if not a.all and (a.project or a.days or a.session_mentions or a.exclude_session):
        ap.error("--project, --days, --session-mentions and --exclude-session need --all")
    rx = re.compile(a.grep, re.I) if a.grep else None
    since = a.since
    if a.days and not since:
        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M")
    max_chars = a.max_chars if a.max_chars is not None else (JSON_MAX_CHARS if a.json else 0)

    if a.all:
        sources = transcripts(a.project, a.days, a.session_mentions, a.subagents, a.exclude_session)
    else:
        path = resolve(a.session)
        sources = [(path, path.parent.name, path.stem)]
        if path.parent.name == "subagents":
            a.subagents = True  # every row of a sub-agent transcript is a sidechain row

    if a.window:
        print_window(sources)
        return

    kept = []
    for path, project, session in sources:
        rows = session_rows(path, project, session, want, a)
        if a.around:
            at = next((i for i, r in enumerate(rows) if r["time"] and r["time"] >= a.around), None)
            if at is None:
                ap.error(f"no entry at or after {a.around} in this session")
            rows = rows[max(0, at - a.context):at + a.context + 1]
        for r in rows:
            if since and r["time"] and r["time"] < since:
                continue
            if a.until and r["time"] and r["time"] >= a.until:
                continue
            if rx and not rx.search(r["text"]):
                continue
            kept.append(r)

    def cut(r):
        if max_chars and r["group"] in ("calls", "tools") and len(r["text"]) > max_chars:
            r = {**r, "text": r["text"][:max_chars] + f"...[{len(r['text']) - max_chars} more]"}
        if max_chars and "input" in r:
            r = {**r, "input": clip_input(r["input"], max_chars)}
        return r

    if a.json:
        body = "".join(json.dumps(cut(r), ensure_ascii=False) + "\n" for r in kept)
        if a.out:
            Path(a.out).write_text(body, encoding="utf-8")
        else:
            sys.stdout.write(body)
        print(f"{len(kept)} rows", file=sys.stderr)
        return

    blocks = []
    for n, r in enumerate(kept, 1):
        r = cut(r)
        text = r["text"]
        if "Base directory for this skill" in text:
            text = text[:300]
        ts = r["time"]
        stamp = f"{r['session'][:8]} {ts[:10]} {ts[11:19]}" if a.all else (ts[11:19] if ts else "")
        blocks.append(f"\n===== [{n}] {r['label']} {stamp} =====\n{text.strip()}\n")
    n = len(blocks)

    total = sum(len(b) for b in blocks)
    if a.chunk_chars:
        chunks, cur, size = [], [], 0
        for b in blocks:
            if cur and size + len(b) > a.chunk_chars:
                chunks.append(cur)
                cur, size = [], 0
            cur.append(b)
            size += len(b)
        if cur:
            chunks.append(cur)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        for i, ch in enumerate(chunks, 1):
            Path(f"{a.out}-{i:03d}.txt").write_text("".join(ch), encoding="utf-8")
        print(f"{n} entries, {total} chars, {len(chunks)} chunks", file=sys.stderr)
    elif a.out:
        Path(a.out).write_text("".join(blocks), encoding="utf-8")
        print(f"{n} entries, {total} chars", file=sys.stderr)
    else:
        sys.stdout.write("".join(blocks))
        print(f"{n} entries, {total} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
