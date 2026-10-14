#!/usr/bin/env python3
# DESC: Report each subagent's requests, context growth and cache use for a Claude session
"""
report-subagent-token-use: For one session, read every subagent transcript and print
what each cost: requests, tool calls, starting and ending context, and cache reads and
creates. Built to measure /vet-fable reviewers (--match 'review|opinion|vet'), but it
reports any subagent.

Context is input + cache-read + cache-created tokens of a request, the size of the
prompt that request sent. Cache reads are billed at a fraction of normal input, so a
long run of requests over a big context is cheap per token but not free.

Output tokens are not reported: the transcripts record streaming snapshots of them, and
the figures are far below the real count.

Subagent transcripts live beside the session: <projects>/<project>/<session>/subagents/.
Examples:
  report-subagent-token-use.py 9e49818b-f213-4c0f-bbb7-bc2cdedf445d
  report-subagent-token-use.py 9e49818b --match 'opinion|review'
  report-subagent-token-use.py /path/to/session.jsonl --json
  report-subagent-token-use.py 9e49818b --json --per-request   # adds each request's context series
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_dirs import config_dirs, find_transcript


def resolve_subagent_dir(arg):
    """The subagents/ directory for a session id (or unique id prefix), or a transcript path."""
    if os.path.isfile(arg):
        transcript = arg
    else:
        transcript, _ = find_transcript(arg) if len(arg) == 36 else (None, None)
        if not transcript:
            hits = []
            for cfg in config_dirs():
                hits += glob.glob(f"{cfg}/projects/*/{arg}*.jsonl")
            if len(hits) > 1:
                sys.exit(f"report-subagent-token-use: '{arg}' matches {len(hits)} sessions; give more of the id")
            transcript = hits[0] if hits else None
    if not transcript:
        sys.exit(f"report-subagent-token-use: no transcript for '{arg}'")
    return os.path.join(transcript[:-len(".jsonl")], "subagents")


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def summarise(path, per_request=False):
    """One subagent's numbers from its transcript, or None when it made no model request.

    With per_request, the row also carries the whole series, one entry per request in order."""
    requests = {}  # message id -> (context, cache_read, cache_created, fresh_input); the last row of an id wins
    tool_calls = 0
    first = last = None
    with open(path) as f:
        for line in f:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            ts = row.get("timestamp")
            if ts:
                first = first or ts
                last = ts
            msg = row.get("message") or {}
            if row.get("type") != "assistant" or not msg.get("usage"):
                continue
            u = msg["usage"]
            read = u.get("cache_read_input_tokens", 0)
            made = u.get("cache_creation_input_tokens", 0)
            fresh = u.get("input_tokens", 0)
            requests[msg.get("id") or row.get("uuid")] = (fresh + read + made, read, made, fresh)
            content = msg.get("content")
            if isinstance(content, list):
                tool_calls += sum(1 for x in content if x.get("type") == "tool_use")
    if not requests:
        return None
    ctx = [r[0] for r in requests.values()]
    meta = {}
    meta_path = path[:-len(".jsonl")] + ".meta.json"
    if os.path.isfile(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    row = {
        "agent": os.path.basename(path)[len("agent-"):-len(".jsonl")],
        "description": meta.get("description", ""),
        "model": meta.get("model", ""),
        "requests": len(ctx),
        "tool_calls": tool_calls,
        "context_start": ctx[0],
        "context_end": ctx[-1],
        "context_growth": ctx[-1] - ctx[0],
        "cache_read": sum(r[1] for r in requests.values()),
        "cache_created": sum(r[2] for r in requests.values()),
        "fresh_input": sum(r[3] for r in requests.values()),
        "seconds": int((parse_ts(last) - parse_ts(first)).total_seconds()) if first and last else 0,
    }
    if per_request:
        row["per_request"] = [{"context": c, "cache_read": rd, "cache_created": mk, "fresh_input": fr}
                              for c, rd, mk, fr in requests.values()]
    return row


def kilo(n):
    return f"{n / 1000:.1f}k"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 3)[-1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="session id (or unique prefix), or a path to the session .jsonl")
    ap.add_argument("--match", metavar="REGEX", help="keep subagents whose description matches (case-insensitive)")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON")
    ap.add_argument("--per-request", action="store_true",
                    help="with --json: add each subagent's per-request series (context, cache read, cache created, fresh input)")
    a = ap.parse_args()

    sub_dir = resolve_subagent_dir(a.session)
    if not os.path.isdir(sub_dir):
        sys.exit(f"report-subagent-token-use: no subagents/ directory at {sub_dir}")
    rows = [r for r in (summarise(p, a.per_request and a.json) for p in sorted(glob.glob(os.path.join(sub_dir, "agent-*.jsonl")))) if r]
    if a.match:
        pat = re.compile(a.match, re.I)
        rows = [r for r in rows if pat.search(r["description"])]
    rows.sort(key=lambda r: r["agent"])
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no subagent made a model request" + (f" matching '{a.match}'" if a.match else ""))
        return
    print(f"{'agent':<10} {'model':<7} {'reqs':>4} {'tools':>5} {'start':>7} {'end':>7} {'growth':>7} "
          f"{'cache read':>10} {'created':>8} {'secs':>5}  description")
    for r in rows:
        print(f"{r['agent'][:8]:<10} {r['model'][:7]:<7} {r['requests']:>4} {r['tool_calls']:>5} "
              f"{kilo(r['context_start']):>7} {kilo(r['context_end']):>7} {kilo(r['context_growth']):>7} "
              f"{kilo(r['cache_read']):>10} {kilo(r['cache_created']):>8} {r['seconds']:>5}  {r['description'][:48]}")
    if len(rows) > 1:
        print(f"{'total':<10} {'':<7} {sum(r['requests'] for r in rows):>4} {sum(r['tool_calls'] for r in rows):>5} "
              f"{'':>7} {'':>7} {'':>7} {kilo(sum(r['cache_read'] for r in rows)):>10} "
              f"{kilo(sum(r['cache_created'] for r in rows)):>8} {sum(r['seconds'] for r in rows):>5}")


if __name__ == "__main__":
    main()
