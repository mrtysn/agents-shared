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
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from transcript_items import items, transcripts  # noqa: E402

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
NUDGE_MAX_CHARS = 400


def entries(path, project, session):
    """One dict per transcript entry (line): its first item's fields plus the
    entry's text blocks joined with a space and whether it carries a tool result."""
    cur = None
    for it in items(path, project, session):
        if cur is None or it["line"] != cur["line"]:
            if cur:
                yield cur
            cur = {**it, "texts": [], "has_result": False}
        if it["group"] in ("tools", "agents") and it["label"].startswith(("TOOL-RESULT", "RESULT")):
            cur["has_result"] = True
        elif it["group"] in ("user", "assistant"):
            cur["texts"].append(it["text"])
    if cur:
        yield cur


def text_of(entry):
    return " ".join(entry["texts"])


def typed_user_text(entry):
    """What the user typed, or None for tool results, injected and sidechain turns."""
    if entry["group"] != "user" or entry["label"] in ("RECAP", "USER(queued)") or entry["sidechain"] or entry["meta"]:
        return None
    if entry["has_result"]:
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


def scan(path, project, session, cutoff):
    events, pending = [], None
    for e in entries(path, project, session):
        ts = parse_ts(e["time"])
        if e["api_error"] and not e["sidechain"]:
            if pending:
                events.append(pending)
            pending = {
                "ts": e["time"] or None,
                "session": e["session"],
                "cwd": e["cwd"],
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
    for path, project, session in transcripts():
        for ev in scan(path, project, session, cutoff):
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
