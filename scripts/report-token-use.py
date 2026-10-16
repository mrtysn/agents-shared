#!/usr/bin/env python3
# DESC: Sum token use per session and per project folder from the transcripts, optionally inside a time window
"""
report-token-use: Read every Claude Code transcript (sub-agent transcripts included, folded
into their parent session) and total the API usage blocks per session and per project.

Per assistant message the transcript records input_tokens, cache_creation_input_tokens,
cache_read_input_tokens and output_tokens. The same message id is written once per
streaming snapshot, so each id is counted once, at its largest value per field. Input and
cache figures are the API's own and exact. Output tokens are the snapshot taken while the
reply streamed, so they undercount the real output: treat them as a lower bound.

A message belongs to the window when its timestamp is inside --since/--until. Totals are
kept per model, because the models are not priced alike.

Each session and project also carries "sub": the part of its total that came from sub-agent
transcripts, so the cost of delegated agents reads apart from the parent session's own.

--cuts t1,t2,... adds "intervals": the weighted tokens between each consecutive pair of times, across
all sessions, for calibrating a quota percentage against the tokens spent between two readings.

Prints one JSON object: {"window", "sessions": [...], "projects": [...]} sorted by
fresh-equivalent tokens (input + 1.25 x cache write + 0.1 x cache read + 5 x output), the
ratios of the standard price list. That sort key is a ranking aid, not the quota's formula.

Examples:
  report-token-use.py                                    # everything on disk
  report-token-use.py --since 2026-10-08T15:00:00Z       # the current weekly window
  report-token-use.py --since 2026-10-15T13:00:00Z --top 10 --text
"""

import argparse
import bisect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcript_items import transcripts  # noqa: E402

FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
SHORT = {"input_tokens": "input", "cache_creation_input_tokens": "cache_write",
         "cache_read_input_tokens": "cache_read", "output_tokens": "output"}


def parse_time(text):
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def weighted(t):
    return t["input"] + 1.25 * t["cache_write"] + 0.1 * t["cache_read"] + 5 * t["output"]


def empty():
    return {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "requests": 0}


def add(into, other):
    for k in into:
        into[k] += other[k]


def read_messages(path):
    """message id -> (timestamp, model, usage), one entry per id at the largest value per field."""
    seen = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if '"usage"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            if not isinstance(u, dict) or not m.get("id"):
                continue
            if m.get("model") in (None, "<synthetic>"):
                continue
            cur = seen.get(m["id"])
            vals = {SHORT[f]: int(u.get(f) or 0) for f in FIELDS}
            if cur is None:
                seen[m["id"]] = (d.get("timestamp", ""), m.get("model"), vals)
            else:
                for k, v in vals.items():
                    cur[2][k] = max(cur[2][k], v)
    return seen


def summarise(since, until, project=None, days=None, cuts=None, buckets=None):
    """cuts: sorted datetimes; buckets: a list filled with the weighted tokens between each pair."""
    sessions = {}
    if buckets is not None:
        buckets[:] = [0.0] * max(len(cuts or []) - 1, 0)
    for path, name, session in transcripts(project=project, days=days, subagents=True):
        key = (name, session)
        s = sessions.setdefault(key, {"project": name, "session": session, "first": None, "last": None,
                                      "total": empty(), "sub": empty(), "models": {}})
        is_sub = "/subagents/" in path
        for ts, model, vals in read_messages(path).values():
            when = parse_time(ts)
            if when is None or (since and when < since) or (until and when >= until):
                continue
            row = {**vals, "requests": 1}
            if buckets is not None:
                slot = bisect.bisect_right(cuts, when) - 1
                if 0 <= slot < len(buckets):
                    buckets[slot] += weighted(vals)
            add(s["total"], row)
            if is_sub:
                add(s["sub"], row)
            add(s["models"].setdefault(model, empty()), row)
            s["first"] = min(filter(None, [s["first"], ts]))
            s["last"] = max(filter(None, [s["last"], ts]))
    rows = [s for s in sessions.values() if s["total"]["requests"]]
    for s in rows:
        s["weighted"] = weighted(s["total"])
    rows.sort(key=lambda s: -s["weighted"])
    folders = {}
    for s in rows:
        p = folders.setdefault(s["project"], {"project": s["project"], "sessions": 0, "total": empty(), "sub": empty(), "models": {}})
        p["sessions"] += 1
        add(p["total"], s["total"])
        add(p["sub"], s["sub"])
        for model, t in s["models"].items():
            add(p["models"].setdefault(model, empty()), t)
    projects = list(folders.values())
    for p in projects:
        p["weighted"] = weighted(p["total"])
    projects.sort(key=lambda p: -p["weighted"])
    return rows, projects


def main():
    ap = argparse.ArgumentParser(description="Total token use per session and project from transcripts.")
    ap.add_argument("--since", help="ISO time, inclusive (e.g. 2026-10-08T15:00:00Z)")
    ap.add_argument("--until", help="ISO time, exclusive")
    ap.add_argument("--project", help="only project folders whose name contains this")
    ap.add_argument("--days", type=int, help="skip transcripts not modified in the last N days")
    ap.add_argument("--top", type=int, help="keep the N biggest sessions and projects")
    ap.add_argument("--cuts", help="comma list of ISO times: also print the weighted tokens between each consecutive pair, as \"intervals\"")
    ap.add_argument("--text", action="store_true", help="print a table instead of JSON")
    a = ap.parse_args()
    since, until = parse_time(a.since), parse_time(a.until)
    cuts = sorted(parse_time(c) for c in a.cuts.split(",")) if a.cuts else None
    buckets = []
    sessions, projects = summarise(since, until, a.project, a.days, cuts, buckets if cuts else None)
    if a.top:
        sessions, projects = sessions[: a.top], projects[: a.top]
    if a.text:
        print(f"{'project':40} {'session':9} {'requests':>8} {'input':>10} {'cache_w':>11} {'cache_r':>13} {'output':>9}")
        for s in sessions:
            t = s["total"]
            print(f"{s['project'][:40]:40} {s['session'][:8]:9} {t['requests']:8} {t['input']:10} "
                  f"{t['cache_write']:11} {t['cache_read']:13} {t['output']:9}")
        return
    out = {"window": {"since": a.since, "until": a.until}, "sessions": sessions, "projects": projects}
    if cuts:
        out["intervals"] = [{"from": cuts[i].isoformat(), "to": cuts[i + 1].isoformat(), "weighted": buckets[i]}
                            for i in range(len(buckets))]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
