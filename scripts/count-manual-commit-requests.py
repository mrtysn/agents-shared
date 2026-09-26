#!/usr/bin/env python3
# DESC: Count how often you had to ask agents to commit or push, by repo and day
"""
count-manual-commit-requests: Count the user messages, over the last N days,
that asked an agent to commit or push — /stg-msg-cmt and its siblings, plus
short typed messages saying "commit", "push" or "cmt". Measures whether
claude/rules/commit-atomically-as-you-build.md is doing its job: the count
should fall once agents commit on their own.

Typed matches are a heuristic; a message that only mentions a commit in passing
is counted too. They are printed so they can be judged by eye.
"""

import argparse
import collections
import datetime
import glob
import json
import os
import re

from claude_dirs import config_dirs

SLASH = re.compile(r"<command-name>/?([\w:-]+)</command-name>")
COMMIT_COMMANDS = {"stg-msg-cmt", "stg-msg", "cmt", "cmt-msg", "send-it", "commit"}
TYPED = re.compile(r"\b(commit|push|cmt)\b", re.I)
HOME_SLUG = os.path.expanduser("~").replace("/", "-") + "-"


def user_text(entry):
    """The text of a message the user typed, or None for tool results and injected turns."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta"):
        return None
    content = entry.get("message", {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    if not isinstance(content, str) or not content.strip():
        return None
    if content.startswith(("<local-command", "<task-notification", "<system-reminder")):
        return None
    return content


def request_kind(text):
    match = SLASH.search(text)
    if match:
        return "/" + match.group(1) if match.group(1) in COMMIT_COMMANDS else None
    return "typed" if len(text) < 400 and TYPED.search(text) else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--days", type=int, default=30, help="how far back to look (default 30)")
    parser.add_argument("--samples", type=int, default=40, help="typed requests to print (default 40)")
    args = parser.parse_args()

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.days)
    sessions, asked_in = set(), set()
    kinds, repos, days = collections.Counter(), collections.Counter(), collections.Counter()
    typed, messages = [], 0

    for config in config_dirs():
        for path in glob.glob(f"{config}/projects/*/*.jsonl"):
            if os.path.getmtime(path) < cutoff.timestamp():
                continue
            repo = os.path.basename(os.path.dirname(path)).removeprefix(HOME_SLUG).removeprefix("dev-") or "~"
            with open(path, errors="ignore") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    stamp = entry.get("timestamp")
                    text = user_text(entry)
                    if not text or not stamp:
                        continue
                    if datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")) < cutoff:
                        continue
                    messages += 1
                    sessions.add(entry.get("sessionId"))
                    kind = request_kind(text)
                    if not kind:
                        continue
                    asked_in.add(entry.get("sessionId"))
                    kinds[kind] += 1
                    repos[repo] += 1
                    days[stamp[:10]] += 1
                    if kind == "typed":
                        typed.append((stamp[:16], repo, " ".join(text.split())[:110]))

    print(f"last {args.days} days: {messages} messages you typed, {len(sessions)} sessions")
    print(f"commit requests: {sum(kinds.values())} in {len(asked_in)} sessions across {len(repos)} repos\n")
    for kind, n in kinds.most_common():
        print(f"  {n:4d}  {kind}")
    print("\nby repo:")
    for repo, n in repos.most_common(15):
        print(f"  {n:4d}  {repo}")
    print("\nby day:")
    for day, n in sorted(days.items()):
        print(f"  {n:4d}  {day}")
    if typed and args.samples:
        print(f"\nlatest typed requests ({len(typed)} in all):")
        for row in sorted(typed)[-args.samples:]:
            print("  ", *row)


if __name__ == "__main__":
    main()
