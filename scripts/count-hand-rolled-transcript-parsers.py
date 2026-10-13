#!/usr/bin/env python3
# DESC: Count tool calls where an agent parsed Claude transcripts by hand instead of using the shared reader
"""
count-hand-rolled-transcript-parsers: how often agents read ~/.claude/projects with
their own python, jq or node instead of scripts/extract-session-text.py, per week.
It measures the failure claude/rules/never-hand-roll-a-transcript-parser.md and
hooks/nudge-transcript-parsers.sh exist to remove, so run it again after the hook
has been live for a while and compare with the baseline below.

A Bash call counts as hand-rolled when its command names a Claude projects folder,
names an interpreter or JSON tool (python, jq, node, json.loads ...) and names none of
the shared readers. A Write call counts when its content names a Claude projects folder
and parses JSON. The patterns match hooks/nudge-transcript-parsers.sh. Every transcript
under every config dir is read through transcript_items.py, sub-agent transcripts included.

Baseline, 60 days to 2026-10-13, before the hook was wired (this session excluded): 350
hand-rolled Bash calls in 79 sessions, 17 calls that named a shared reader (10 sessions),
11 Write calls that wrote a parser (6 sessions). It counts every session that touched
transcripts, not only those where the user asked for log mining.

Usage:
  count-hand-rolled-transcript-parsers.py [--days N] [--exclude-session ID] [--json]
"""

import argparse
import collections
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcript_items import items, transcripts  # noqa: E402

PATH_RE = re.compile(r"claude[A-Za-z0-9_.*-]*/projects|CLAUDE_CONFIG_DIR\S*/projects")
RUN_RE = re.compile(r"(^|[^\w.-])(python[0-9.]*|jq|node|deno|bun|ruby|perl)([^\w.-]|$)|json\.loads|JSON\.parse")
JSON_RE = re.compile(r"json\.loads|json\.load\(|import json|JSON\.parse|(^|[^\w.-])jq([^\w.-]|$)")
SHARED_RE = re.compile(
    r"extract-session-text|search-history|find-repeated-user-prompts|find-interrupted-responses|find-listed-unasked|"
    r"find-invisible-output|recent-sessions|blame-session|iterm-revive|report-subagent-token-use|review-ssh-guard-asks|"
    r"usage-survey|command-moments-survey|count-manual-commit|survey-remote-commands|memory-audit|transcript_items|"
    r"count-hand-rolled-transcript-parsers"
)


def classify(row):
    """'hand-rolled', 'shared' or None for one call row."""
    text = row["text"] if row["tool"] == "Bash" else (row["input"].get("content") or "")
    if row["tool"] == "Bash":
        if not (PATH_RE.search(text) and RUN_RE.search(text)):
            return None
        return "shared" if SHARED_RE.search(text) else "hand-rolled"
    if row["tool"] == "Write" and PATH_RE.search(text) and JSON_RE.search(text):
        return "write"
    return None


def main():
    ap = argparse.ArgumentParser(description="Count hand-rolled transcript parsers per week.")
    ap.add_argument("--days", type=int, default=60, help="look back this many days (default 60)")
    ap.add_argument("--exclude-session", action="append", default=[], metavar="ID", help="leave out a session (id prefix)")
    ap.add_argument("--json", action="store_true", help="print the counts as JSON")
    a = ap.parse_args()

    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M")
    calls = collections.Counter()
    sessions = collections.defaultdict(set)
    weeks = collections.defaultdict(collections.Counter)
    for path, project, session in transcripts(days=a.days, subagents=True, exclude=a.exclude_session):
        for row in items(str(path), project, session, want={"calls"}):
            if row["time"] < cutoff or row.get("tool") not in ("Bash", "Write"):
                continue
            kind = classify(row)
            if not kind:
                continue
            calls[kind] += 1
            sessions[kind].add(session)
            week = datetime.datetime.fromisoformat(row["time"].replace("Z", "+00:00")).strftime("%G-W%V")
            weeks[week][kind] += 1
    out = {
        "days": a.days,
        "calls": dict(calls),
        "sessions": {k: len(v) for k, v in sessions.items()},
        "per_week": {w: dict(c) for w, c in sorted(weeks.items())},
    }
    if a.json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return
    print(f"last {a.days} days: hand-rolled {calls['hand-rolled']} calls in {len(sessions['hand-rolled'])} sessions; "
          f"shared reader named {calls['shared']} calls in {len(sessions['shared'])} sessions; "
          f"parser written with Write {calls['write']} in {len(sessions['write'])} sessions")
    for week, c in sorted(weeks.items()):
        print(f"  {week}  hand-rolled {c['hand-rolled']:4}  shared {c['shared']:3}  write {c['write']:3}")


if __name__ == "__main__":
    main()
