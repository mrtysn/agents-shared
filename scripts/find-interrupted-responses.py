#!/usr/bin/env python3
# DESC: List every dropped-connection API error in Claude transcripts and what the user typed next
"""
find-interrupted-responses: Walk every transcript and find the synthetic API-error
turns that mean a response was cut off (connection lost, response stopped arriving,
computer slept, server error, rate limit, ...). For each, report the next message
the user typed and whether it was a manual nudge to carry on ("continue", "go on",
a pasted copy of the error) or an unrelated prompt.

Rate-limit and policy refusals are listed as errors but not as interruptions:
retrying them is not the same as nudging a dropped stream.

    find-interrupted-responses.py [--days N] [--json]
"""

import argparse
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

DROPPED = re.compile(
    r"response stopped arriving|connection lost|went to sleep mid-response|"
    r"can't reach the api server|500 internal server|529 overloaded|"
    r"stream.*(ended|closed|idle)|socket|ECONNRESET|timed out",
    re.I,
)
NUDGE = re.compile(
    r"\b(continue|carry on|go on|keep going|proceed|resume|retry|try again|pick up|finish|where you left)\b|api error",
    re.I,
)
HOME_SLUG = os.path.expanduser("~").replace("/", "-") + "-"
NUDGE_MAX_CHARS = 400


def text_of(entry):
    content = entry.get("message", {}).get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


def typed_user_text(entry):
    """What the user typed, or None for tool results, injected and sidechain turns."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta"):
        return None
    content = entry.get("message", {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    t = text_of(entry).strip()
    if not t or t.startswith(("<system-reminder", "<command-", "<local-command", "<task-notification")):
        return None
    return t


def parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def scan(path, cutoff):
    events, pending = [], None
    with open(path) as fh:
        for line in fh:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ts = parse_ts(e.get("timestamp"))
            if e.get("isApiErrorMessage") and not e.get("isSidechain"):
                if pending:
                    events.append(pending)
                pending = {
                    "ts": e.get("timestamp"),
                    "session": e.get("sessionId") or os.path.basename(path)[:-6],
                    "cwd": e.get("cwd", ""),
                    "error": text_of(e).strip()[:160],
                    "dropped": bool(DROPPED.search(text_of(e))),
                    "next": None,
                    "gap_s": None,
                }
                pending["_t"] = ts
                continue
            if pending:
                t = typed_user_text(e)
                if t is not None:
                    pending["next"] = t[:300]
                    if ts and pending["_t"]:
                        pending["gap_s"] = int((ts - pending["_t"]).total_seconds())
                    pending["nudge"] = len(t) <= NUDGE_MAX_CHARS and bool(NUDGE.search(t))
                    events.append(pending)
                    pending = None
    if pending:
        events.append(pending)
    for ev in events:
        ev.pop("_t", None)
        ev.setdefault("nudge", False)
    if cutoff:
        events = [ev for ev in events if (parse_ts(ev["ts"]) or cutoff) >= cutoff]
    return events


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, help="only errors from the last N days")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = ap.parse_args()
    cutoff = None
    if a.days:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=a.days)
    out = []
    for d in config_dirs():
        for path in glob.glob(f"{d}/projects/*/*.jsonl"):
            project = os.path.basename(os.path.dirname(path)).removeprefix(HOME_SLUG)
            for ev in scan(path, cutoff):
                ev["project"] = project
                out.append(ev)
    out.sort(key=lambda ev: ev["ts"] or "")
    if a.json:
        json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
        return
    for ev in out:
        mark = "NUDGE" if ev["nudge"] else ("drop " if ev["dropped"] else "other")
        print(f"{(ev['ts'] or '')[:16]}  {mark}  {ev['project'][:28]:28}  {ev['error'][:60]!r}  -> {(ev['next'] or '(none)')[:70]!r}")


if __name__ == "__main__":
    main()
