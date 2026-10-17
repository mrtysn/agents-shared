#!/usr/bin/env python3
# DESC: Sum token use per session and per project folder from the transcripts, optionally inside a time window
"""
report-token-use: Read every Claude Code transcript (sub-agent transcripts included, folded
into their parent session) and total the API usage blocks per session and per project, with a
cost in dollars at Anthropic's list prices.

Per assistant message the transcript records input_tokens, cache_creation_input_tokens,
cache_read_input_tokens and output_tokens. The same message id is written once per
streaming snapshot, so each id is counted once, at its largest value per field. Input and
cache figures are the API's own and exact. Output tokens are the snapshot taken while the
reply streamed, so they undercount the real output, by about 2x (1.5 to 2.5x) by a check
against Claude Code's own session cost on 2026-10-16. With the scale of 2 below, the summed
cost of 62 sessions over $20 came to 88% of the cost Claude Code itself reported for them
(median per session 97%); calls that leave no transcript row, such as the status line's
title and topic calls, are the likeliest part of the rest.

A message belongs to the window when its timestamp is inside --since/--until. Totals are
kept per model, because the models are not priced alike.

"cost" is the list price in dollars, from the model's own row in PRICES (the pricing page,
read 2026-10-17): cache writes at the 1-hour price for the part the usage block marks
ephemeral_1h (and for a whole write when it carries no split, since 1-hour writes are what
this machine's transcripts hold), cache reads at the model's read price, output at its price
times OUTPUT_SCALE for the undercount. A model with no row costs nothing and is listed under
"unpriced". The plan quota's own formula is unpublished: cost is a ranking and calibration
aid, not what the plan charges.

Each session carries "title", the last ai-title its transcript records (null when it has none), and
sessions and projects carry "first" and "last", the times of their earliest and latest message in the
window. Each also carries "sub": the part of its total that came from sub-agent
transcripts, so the cost of delegated agents reads apart from the parent session's own.

Totals also count cache rewrites: a request whose cache read falls below half of the previous
request's prompt in the same transcript while its own prompt stays at least 80% as large (so not
a compaction), with at least 20,000 tokens written. The cache had expired or been dropped, and
the whole context was written again at the write price. "rewrites" counts them,
"rewrite_tokens" and "rewrite_cost" are what they wrote, and "rewrites_after_idle" counts those
that followed a gap of 5 minutes or more since the previous request: an agent left waiting on a
long job pays its full context again on its next request.

--cuts t1,t2,... adds "intervals": the cost between each consecutive pair of times, across
all sessions, for calibrating a quota percentage against the spend between two readings.

Prints one JSON object: {"window", "output_scale", "unpriced", "sessions": [...], "projects": [...]}
sorted by cost.

Examples:
  report-token-use.py                                    # everything on disk
  report-token-use.py --since 2026-10-08T15:00:00Z       # the current weekly window
  report-token-use.py --since 2026-10-15T13:00:00Z --top 10 --text
"""

import argparse
import bisect
import json
import re
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


# (model id regex, input, 5-minute write, 1-hour write, cache read, output), dollars per million
# tokens. First match wins. Haiku 5.5 has a second row above 100,000 prompt tokens.
PRICES = [
    (r"^claude-fable-5-1", 10, 12.5, 20, 0.25, 50),
    (r"^claude-fable-5", 10, 12.5, 20, 1, 50),
    (r"^claude-opus-5-5", 4, 5, 8, 0.20, 20),
    (r"^claude-opus-5", 5, 6.25, 10, 0.5, 25),
    (r"^claude-opus-4-[5-8]", 5, 6.25, 10, 0.5, 25),
    (r"^claude-opus-4", 15, 18.75, 30, 1.5, 75),
    (r"^claude-sonnet-5-5", 2, 2.5, 4, 0.10, 10),
    (r"^claude-sonnet-5", 2, 2.5, 4, 0.20, 10),
    (r"^claude-sonnet-4", 3, 3.75, 6, 0.3, 15),
    (r"^claude-haiku-5-5", 0.10, 0.125, 0.20, 0.01, 0.50),
    (r"^claude-haiku-4-5", 1, 1.25, 2, 0.1, 5),
]
HAIKU_55_LONG = (0.50, 0.625, 1, 0.05, 2.50)  # prompts over 100,000 tokens
OUTPUT_SCALE = 2.0


def price_of(model, prompt_tokens):
    for pattern, *row in PRICES:
        if re.match(pattern, model or ""):
            if pattern == r"^claude-haiku-5-5" and prompt_tokens > 100_000:
                return HAIKU_55_LONG
            return tuple(row)
    return None


def message_cost(model, v, output_scale=OUTPUT_SCALE):
    """Dollars for one message's usage v, or None when the model has no price row."""
    price = price_of(model, v["input"] + v["cache_read"] + v["cache_write"])
    if price is None:
        return None
    p_in, p_w5, p_w1, p_read, p_out = price
    w1 = min(v["write_1h"], v["cache_write"])
    return (v["input"] * p_in + (v["cache_write"] - w1) * p_w5 + w1 * p_w1
            + v["cache_read"] * p_read + v["output"] * output_scale * p_out) / 1e6


REWRITE_READ_SHARE = 0.5   # cache read below this share of the previous prompt
REWRITE_KEEP_SHARE = 0.8   # while the prompt keeps at least this share (not a compaction)
REWRITE_MIN_WRITE = 20_000
IDLE_SECONDS = 300


def is_rewrite(vals, prompt, prev_prompt):
    return bool(prev_prompt and vals["cache_read"] < REWRITE_READ_SHARE * prev_prompt
                and prompt >= REWRITE_KEEP_SHARE * prev_prompt and vals["cache_write"] >= REWRITE_MIN_WRITE)


def empty():
    return {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "requests": 0, "cost": 0.0,
            "rewrites": 0, "rewrites_after_idle": 0, "rewrite_tokens": 0, "rewrite_cost": 0.0}


def add(into, other):
    for k in into:
        into[k] += other[k]


def read_messages(path, titles=None):
    """message id -> (timestamp, model, usage), one entry per id at the largest value per field.

    titles: a list that gets each ai-title the file records (Claude Code's own name for the session)."""
    seen = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if titles is not None and '"ai-title"' in raw:
                try:
                    title = json.loads(raw).get("aiTitle")
                except json.JSONDecodeError:
                    title = None
                if title:
                    titles.append(title)
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
            split = u.get("cache_creation")
            vals["write_1h"] = (int(split.get("ephemeral_1h_input_tokens") or 0) if isinstance(split, dict)
                                else vals["cache_write"])
            if cur is None:
                seen[m["id"]] = (d.get("timestamp", ""), m.get("model"), vals)
            else:
                for k, v in vals.items():
                    cur[2][k] = max(cur[2][k], v)
    return seen


def summarise(since, until, project=None, days=None, cuts=None, buckets=None, unpriced=None,
              output_scale=OUTPUT_SCALE):
    """cuts: sorted datetimes; buckets: a list filled with the cost between each pair;
    unpriced: a dict filled with the requests of each model that has no price row."""
    sessions = {}
    if buckets is not None:
        buckets[:] = [0.0] * max(len(cuts or []) - 1, 0)
    for path, name, session in transcripts(project=project, days=days, subagents=True):
        key = (name, session)
        s = sessions.setdefault(key, {"project": name, "session": session, "title": None, "first": None,
                                      "last": None, "total": empty(), "sub": empty(), "models": {}})
        is_sub = "/subagents/" in path
        titles = None if is_sub else []
        prev_prompt = prev_when = None
        for ts, model, vals in sorted(read_messages(path, titles).values(), key=lambda m: m[0] or ""):
            when = parse_time(ts)
            prompt = vals["input"] + vals["cache_read"] + vals["cache_write"]
            rewrite = is_rewrite(vals, prompt, prev_prompt)
            idle = bool(rewrite and when and prev_when and (when - prev_when).total_seconds() >= IDLE_SECONDS)
            prev_prompt, prev_when = prompt, when
            if when is None or (since and when < since) or (until and when >= until):
                continue
            cost = message_cost(model, vals, output_scale)
            if cost is None:
                cost = 0.0
                if unpriced is not None:
                    unpriced[model] = unpriced.get(model, 0) + 1
            row = {k: vals[k] for k in ("input", "cache_write", "cache_read", "output")}
            rewrite_cost = 0.0
            if rewrite:
                written = {"input": 0, "cache_read": 0, "output": 0, "cache_write": vals["cache_write"],
                           "write_1h": vals["write_1h"]}
                rewrite_cost = message_cost(model, written, output_scale) or 0.0
            row.update(requests=1, cost=cost, rewrites=int(rewrite), rewrites_after_idle=int(idle),
                       rewrite_tokens=vals["cache_write"] if rewrite else 0, rewrite_cost=rewrite_cost)
            if buckets is not None:
                slot = bisect.bisect_right(cuts, when) - 1
                if 0 <= slot < len(buckets):
                    buckets[slot] += cost
            add(s["total"], row)
            if is_sub:
                add(s["sub"], row)
            add(s["models"].setdefault(model, empty()), row)
            s["first"] = min(filter(None, [s["first"], ts]))
            s["last"] = max(filter(None, [s["last"], ts]))
        if titles:
            s["title"] = titles[-1]
    rows = [s for s in sessions.values() if s["total"]["requests"]]
    rows.sort(key=lambda s: -s["total"]["cost"])
    folders = {}
    for s in rows:
        p = folders.setdefault(s["project"], {"project": s["project"], "sessions": 0, "first": None, "last": None,
                                              "total": empty(), "sub": empty(), "models": {}})
        p["sessions"] += 1
        p["first"] = min(filter(None, [p["first"], s["first"]]))
        p["last"] = max(filter(None, [p["last"], s["last"]]))
        add(p["total"], s["total"])
        add(p["sub"], s["sub"])
        for model, t in s["models"].items():
            add(p["models"].setdefault(model, empty()), t)
    projects = list(folders.values())
    projects.sort(key=lambda p: -p["total"]["cost"])
    return rows, projects


def main():
    ap = argparse.ArgumentParser(description="Total token use and list-price cost per session and project from transcripts.")
    ap.add_argument("--since", help="ISO time, inclusive (e.g. 2026-10-08T15:00:00Z)")
    ap.add_argument("--until", help="ISO time, exclusive")
    ap.add_argument("--project", help="only project folders whose name contains this")
    ap.add_argument("--days", type=int, help="skip transcripts not modified in the last N days")
    ap.add_argument("--top", type=int, help="keep the N biggest sessions and projects")
    ap.add_argument("--cuts", help="comma list of ISO times: also print the cost between each consecutive pair, as \"intervals\"")
    ap.add_argument("--output-scale", type=float, default=OUTPUT_SCALE,
                    help=f"multiplier for the recorded output tokens (default {OUTPUT_SCALE}; 1 = as recorded)")
    ap.add_argument("--text", action="store_true", help="print a table instead of JSON")
    a = ap.parse_args()
    since, until = parse_time(a.since), parse_time(a.until)
    cuts = sorted(parse_time(c) for c in a.cuts.split(",")) if a.cuts else None
    buckets, unpriced = [], {}
    sessions, projects = summarise(since, until, a.project, a.days, cuts, buckets if cuts else None, unpriced,
                                   a.output_scale)
    if a.top:
        sessions, projects = sessions[: a.top], projects[: a.top]
    if a.text:
        print(f"{'project':40} {'session':9} {'requests':>8} {'cost $':>9} {'cache_w':>11} {'cache_r':>13} "
              f"{'output':>9} {'rewrites':>8} {'idle':>5} {'rewrite $':>9}")
        for s in sessions:
            t = s["total"]
            print(f"{s['project'][:40]:40} {s['session'][:8]:9} {t['requests']:8} {t['cost']:9.2f} "
                  f"{t['cache_write']:11} {t['cache_read']:13} {t['output']:9} {t['rewrites']:8} "
                  f"{t['rewrites_after_idle']:5} {t['rewrite_cost']:9.2f}")
        if unpriced:
            print(f"unpriced (counted as $0): {unpriced}")
        return
    out = {"window": {"since": a.since, "until": a.until}, "output_scale": a.output_scale,
           "unpriced": unpriced, "sessions": sessions, "projects": projects}
    if cuts:
        out["intervals"] = [{"from": cuts[i].isoformat(), "to": cuts[i + 1].isoformat(), "cost": buckets[i]}
                            for i in range(len(buckets))]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
