#!/usr/bin/env python3
# DESC: Survey transcripts for the user's own prompts asking for sub-agent spawns as sanity checks or reviews
"""find-subagent-sanity-check-requests: list the human-typed prompts in recent
transcripts that ask the assistant to spawn sub-agents (or "another agent",
"a fresh pair of eyes") to check, review, verify or sanity-check work.

A prompt matches when it names a spawn ("subagent", "sub-agent", "spawn",
"fresh agent", "second opinion", "independent review") and, within the same
prompt, a checking word ("sanity", "verify", "review", "double check",
"audit", "critic", "challenge", "validate"). Both lists are in the script.

Output:
  default    counts per week, per project, per signal word, plus one line per
             match (time, project, session, first 160 chars)
  --json     the matches as JSON, full prompt text included
  --full     the whole prompt under each match

Transcripts come from claude_dirs.config_dirs(). Sub-agent (sidechain) turns,
tool results, task notifications and slash-command expansions are not the
user's words and are skipped; the prompt a skill expanded to is skipped too.
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

SPAWN_RE = re.compile(
    r"(sub-?\s?agents?|(fable|opus|sonnet|haiku) agents?|spawn (a|an|another|one|two|some|\w+) (\w+ )?agents?|fresh (agent|eyes)|another agent|"
    r"second (opinion|pair)|unbiased opinion|independent(ly)? (review|check|verif)|new agent|separate agent|"
    r"agents? (to|that|who) (check|review|verify|audit|vet)|blind (agent|review))",
    re.I,
)
CHECK_RE = re.compile(
    r"(sanity|verif(y|ied|ication)|double.?check|cross.?check|review|audit|\bcritic\b|challenge|"
    r"validate|\bvet\b|opinion|assessment|advice|\binput\b|second opinion|unbiased|fresh eyes|pair of eyes|poke holes|red.?team|\bconfirm\b|holes in)",
    re.I,
)
SIGNALS = ["sanity", "verify", "double check", "review", "audit", "vet", "opinion", "assessment", "advice", "input", "critic", "challenge", "validate", "unbiased",
           "fresh eyes", "second opinion", "holes in", "confirm"]


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
    ap.add_argument("--json", action="store_true", help="matches as JSON with full text")
    ap.add_argument("--full", action="store_true", help="print the whole prompt under each match")
    ap.add_argument("--max-chars", type=int, default=3000,
                    help="ignore prompts longer than this: pasted logs and handoffs, not requests (default 3000)")
    args = ap.parse_args()

    total = 0
    sessions = set()
    matches = []
    for p in scan(args.days):
        total += 1
        sessions.add(p["session"])
        t = p["text"]
        if len(t) > args.max_chars:
            continue
        if t.startswith("Reply with exactly"):
            continue
        if SPAWN_RE.search(t) and CHECK_RE.search(t):
            matches.append(p)
    matches.sort(key=lambda m: m["time"])

    if args.json:
        json.dump(matches, sys.stdout, indent=1)
        return

    print(f"window: last {args.days} days · {total} human prompts in {len(sessions)} sessions · "
          f"{len(matches)} matches ({100 * len(matches) / max(total, 1):.1f}% of prompts)")
    weeks = collections.Counter(datetime.fromisoformat(m["time"].replace("Z", "+00:00")).strftime("%G-W%V") for m in matches)
    print("\nper week:", ", ".join(f"{w}={n}" for w, n in sorted(weeks.items())))
    print("\nper project:", ", ".join(f"{p}={n}" for p, n in collections.Counter(m["project"] for m in matches).most_common()))
    sig = collections.Counter(s for m in matches for s in SIGNALS if s in m["text"].lower())
    print("\nsignal words:", ", ".join(f"{s}={n}" for s, n in sig.most_common()))
    print("\nmatches in sessions:", len({m["session"] for m in matches}))
    print()
    for m in matches:
        head = m["text"].replace("\n", " ")[:160]
        print(f"{m['time'][:16]} {m['project'][:18]:18} {m['session'][:8]}  {head}")
        if args.full:
            print("    " + m["text"].replace("\n", "\n    ") + "\n")


if __name__ == "__main__":
    main()
