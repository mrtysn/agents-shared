#!/usr/bin/env python3
# DESC: Survey transcripts for the user's own prompts asking for sub-agent spawns as sanity checks or reviews
"""find-repeated-user-prompts: list the human-typed prompts in recent
transcripts that look like a given request, so a phrase the user keeps typing
can be counted and read in context.

A prompt matches when every --pattern regex matches it, ignoring case (use
alternation inside one regex for "this or that"). Prompts over --max-chars (pasted logs,
handoffs) and prompts starting with a --skip-prefix are not requests and are
left out.

Output:
  default    counts per week, project and day, then one line per match (time,
             project, session, first 160 chars)
  --json     the matches as JSON, full prompt text included
  --full     the whole prompt under each match

Example (asks for a fresh sub-agent to check work):
  find-repeated-user-prompts.py --days 30 --skip-prefix 'Reply with exactly' \\
    --pattern 'sub-?agent|(fable|opus) agent' --pattern 'review|vet|opinion|unbiased|sanity'

Transcripts come from claude_dirs.config_dirs(). Sub-agent (sidechain) turns,
tool results, task notifications and slash-command expansions are not the
user's words and are skipped.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def human_prompt(e):
    if e.get("type") != "user" or e.get("isSidechain") or e.get("isMeta"):
        return None
    if (e.get("origin") or {}).get("kind") != "human":
        return None
    content = e["message"]["content"]
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    text = text_of(content).strip()
    if not text or text.startswith(("<task-notification", "<local-command", "[Request interrupted", "<command-")):
        return None
    return text


def project_of(path):
    name = os.path.basename(os.path.dirname(path))
    return re.sub(r"^-Users-[^-]+-dev-?", "", name) or "dev"


def scan(days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    seen = set()
    for cfg in config_dirs():
        for path in glob.glob(f"{cfg}/projects/*/*.jsonl"):
            if datetime.fromtimestamp(os.path.getmtime(path), timezone.utc) < cutoff:
                continue
            try:
                with open(path) as f:
                    entries = [json.loads(line) for line in f]
            except (OSError, json.JSONDecodeError):
                continue
            for e in entries:
                text = human_prompt(e)
                ts = e.get("timestamp", "")
                if not text or not ts or datetime.fromisoformat(ts.replace("Z", "+00:00")) < cutoff:
                    continue
                key = (e.get("sessionId"), ts)
                if key in seen:
                    continue
                seen.add(key)
                yield {
                    "time": ts, "project": project_of(path), "session": e.get("sessionId"), "text": text,
            }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--days", type=int, default=30, help="look back this many days (default 30)")
    ap.add_argument("--pattern", action="append", default=[], metavar="REGEX",
                    help="regex every match must contain (repeatable, ANDed)")
    ap.add_argument("--skip-prefix", action="append", default=[], metavar="TEXT",
                    help="ignore prompts starting with TEXT (repeatable)")
    ap.add_argument("--max-chars", type=int, default=3000, help="ignore longer prompts (default 3000)")
    ap.add_argument("--json", action="store_true", help="matches as JSON with full text")
    ap.add_argument("--full", action="store_true", help="print the whole prompt under each match")
    args = ap.parse_args()
    if not args.pattern:
        ap.error("give at least one --pattern regex")

    patterns = [re.compile(r, re.I) for r in args.pattern]
    total, sessions, matches = 0, set(), []
    for p in scan(args.days):
        total += 1
        sessions.add(p["session"])
        t = p["text"]
        if len(t) > args.max_chars or t.startswith(tuple(args.skip_prefix)):
            continue
        if all(r.search(t) for r in patterns):
            matches.append(p)
    matches.sort(key=lambda m: m["time"])

    if args.json:
        json.dump(matches, sys.stdout, indent=1)
        return

    def when(m):
        return datetime.fromisoformat(m["time"].replace("Z", "+00:00"))

    print(f"window: last {args.days} days · {total} human prompts in {len(sessions)} sessions · "
          f"{len(matches)} matches in {len({m['session'] for m in matches})} sessions "
          f"({100 * len(matches) / max(total, 1):.1f}% of prompts)")
    weeks = collections.Counter(when(m).strftime("%G-W%V") for m in matches)
    print("\nper week:", ", ".join(f"{w}={n}" for w, n in sorted(weeks.items())))
    days = collections.Counter(m["time"][:10] for m in matches)
    print("busiest days:", ", ".join(f"{d}={n}" for d, n in days.most_common(5)))
    print("per project:", ", ".join(f"{p}={n}" for p, n in collections.Counter(m["project"] for m in matches).most_common()))
    print()
    for m in matches:
        head = m["text"].replace("\n", " ")[:160]
        print(f"{m['time'][:16]} {m['project'][:18]:18} {m['session'][:8]}  {head}")
        if args.full:
            print("    " + m["text"].replace("\n", "\n    ") + "\n")


if __name__ == "__main__":
    main()
