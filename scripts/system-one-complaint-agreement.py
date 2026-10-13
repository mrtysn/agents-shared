#!/usr/bin/env python3
# DESC: Score the system-one stop and ask hooks' shadow verdicts against the user's real complaints
"""
system-one-complaint-agreement: ground the stop and ask hooks in what the user
actually did. For each shadow verdict row, find the user's reaction in the
transcript and report how often the hook fired where the user complained, and
how often it fired where they did not.

  stop  A complaint is the next typed message after the reply asking for it to
        be simpler or explained ("say it simpler", "I dont understand", "what
        does this mean", "explain"). The hook fires on `overlong` or
        `needless_table`.
  ask   A complaint is a question prompt the user dismissed
        (AskUserQuestion answered with a rejection). Verdict rows are matched
        to the tool call by session and time (within MATCH_SECONDS).

Read the numbers for what the labels are, not as a grade of the hooks: the stop
hook scores padding and needless tables (not jargon the reader cannot follow),
and the ask hook scores whether a question was already answered or is a routine
default (not whether it lacked explanation). A low score means the hook's
question is a different one from the complaint, not that it is miscalibrated.

It reads the verdict's own `fired` list, so it never re-runs the model or
re-derives a threshold. With --days N only rows from the last N days count.

    system-one-complaint-agreement.py [--days N] [--json]
"""

import argparse
import bisect
import collections
import datetime
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

STATE_DIR = os.environ.get("SYSTEM_ONE_STATE_DIR", os.path.expanduser("~/.local/state/system-one"))
COMPLAINT = re.compile(
    r"say it simpler|simpler\b|i (dont|don't|do not) (get|understand)|what does (this|that) mean|"
    r"what is this|explain|not enough context|wtf are you saying|what are you saying",
    re.I,
)
MATCH_SECONDS = 15


def parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def content_text(entry):
    c = entry.get("message", {}).get("content")
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(c, str):
        return None
    c = c.strip()
    if not c or c.startswith(("<", "[Request interrupted")):
        return None
    return c


def index_sessions():
    """session id -> (sorted typed-message times with texts, AskUserQuestion calls with times and dismissed flag)."""
    out = {}
    for d in config_dirs():
        for path in glob.glob(f"{d}/projects/*/*.jsonl"):
            sid = os.path.basename(path)[:-6]
            typed, asks, ids = [], [], {}
            with open(path) as fh:
                for line in fh:
                    if '"user"' not in line and "AskUserQuestion" not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except ValueError:
                        continue
                    if e.get("isSidechain"):
                        continue
                    ts = parse_ts(e.get("timestamp"))
                    if ts is None:
                        continue
                    c = e.get("message", {}).get("content")
                    if e.get("type") == "assistant" and isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                                ids[b["id"]] = len(asks)
                                asks.append([ts, False])
                    elif e.get("type") == "user":
                        if isinstance(c, list):
                            for b in c:
                                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in ids:
                                    if "doesn't want to proceed" in json.dumps(b.get("content")):
                                        asks[ids[b["tool_use_id"]]][1] = True
                        if not e.get("isMeta"):
                            t = content_text(e)
                            if t:
                                typed.append((ts, t))
            typed.sort()
            out[sid] = (typed, asks)
    return out


def rows(hook, cutoff):
    for path in glob.glob(f"{STATE_DIR}/shadow/{hook}/*.jsonl"):
        with open(path) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") == "outcome" or "answers" not in r:
                    continue
                r["ts_epoch"] = epoch(r)
                if r["ts_epoch"] is None or (cutoff and r["ts_epoch"] < cutoff):
                    continue
                yield r


def epoch(r):
    if r.get("ts_epoch"):
        return r["ts_epoch"]
    try:
        return datetime.datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except (KeyError, ValueError):
        return None


def tally(pairs):
    """pairs: (complained, fired). Returns counts and rates."""
    c = collections.Counter((a, b) for a, b in pairs)
    n = len(pairs)
    pos = c[(True, True)] + c[(True, False)]
    fired = c[(True, True)] + c[(False, True)]
    return {
        "rows": n,
        "complaints": pos,
        "fired": fired,
        "fired_on_complaint": c[(True, True)],
        "recall": round(c[(True, True)] / pos, 3) if pos else None,
        "precision": round(c[(True, True)] / fired, 3) if fired else None,
        "fire_rate_without_complaint": round(c[(False, True)] / (n - pos), 3) if n - pos else None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cutoff = None
    if a.days:
        cutoff = datetime.datetime.now().timestamp() - a.days * 86400
    sessions = index_sessions()
    stop_pairs, ask_pairs = [], []
    for r in rows("stop", cutoff):
        typed, _ = sessions.get(r["session_id"], ([], []))
        times = [t for t, _ in typed]
        i = bisect.bisect_right(times, r["ts_epoch"])
        if i >= len(typed):
            continue
        stop_pairs.append((bool(COMPLAINT.search(typed[i][1][:200])), bool(r.get("fired"))))
    for r in rows("ask", cutoff):
        _, asks = sessions.get(r["session_id"], ([], []))
        near = [x for x in asks if abs(x[0] - r["ts_epoch"]) <= MATCH_SECONDS]
        if not near:
            continue
        ask_pairs.append((near[0][1], bool(r.get("fired"))))
    result = {"stop": tally(stop_pairs), "ask": tally(ask_pairs)}
    if a.json:
        json.dump(result, sys.stdout, indent=1)
        return
    for hook, t in result.items():
        print(f"{hook}: {t}")


if __name__ == "__main__":
    main()
