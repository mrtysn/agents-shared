#!/usr/bin/env python3
# DESC: Pair each "why did you / where did you get / wdym" prompt with the agent's reply, for classifying how agents answer a challenge
"""
find-why-question-answers: candidates for the survey "when the user asks why an
agent wrote, claimed or did something, how did the agent answer?".

Each typed user prompt that matches the why-pattern becomes one JSONL row:
  id, session, project, time, user   the prompt
  before                             the agent's last text before it (tail, 1200 chars)
  after                              the agent's text in the next few rows (head, 1500 chars)

The rows are then classified (mine-chat-logs step 4) into: MECHANISM (named what
produced the output), CONTRITION (apology or a story of a held view, no cause),
SWITCH (adopted the user's view silently), DEFEND (evidence), ACTION (acted
instead of answering), OTHER. communication-style.md asks for MECHANISM.

Reads transcripts only through extract-session-text.py. Read-only.

Usage:
  find-why-question-answers.py --days 30 --exclude-session <id> > pairs.jsonl
  find-why-question-answers.py --rows rows.jsonl        pair rows already extracted
  find-why-question-answers.py --pattern 'REGEX'        replace the default why-pattern
"""

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_PATTERN = (
    r"(?i)(why (did|would|are|is|do) you|where did you get|why the (fuck|hell)|wdym"
    r"|what is this suggestion|why are you (saying|making|writing)|who said)"
)
MAX_PROMPT = 1500  # longer prompts are pastes, not questions


def load_rows(args):
    if args.rows:
        with open(args.rows, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    reader = os.path.join(os.path.dirname(os.path.realpath(__file__)), "extract-session-text.py")
    cmd = [sys.executable, reader, "--all", "--days", str(args.days),
           "--kinds", "user,assistant", "--json"]
    for s in args.exclude_session:
        cmd += ["--exclude-session", s]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def pair(rows, pattern, lookahead=6):
    rx = re.compile(pattern)
    for i, r in enumerate(rows):
        text = r.get("text") or ""
        if r.get("group") != "user" or r.get("origin") != "human":
            continue
        if len(text) >= MAX_PROMPT or not rx.search(text):
            continue
        sess = r.get("session")
        before = [x.get("text") or "" for x in rows[max(0, i - 3):i]
                  if x.get("group") == "assistant" and x.get("session") == sess]
        after = [x.get("text") or "" for x in rows[i + 1:i + lookahead]
                 if x.get("group") == "assistant" and x.get("session") == sess]
        yield {
            "id": i, "session": sess, "project": r.get("project"), "time": r.get("time"),
            "user": text,
            "before": (before[-1] if before else "")[-1200:],
            "after": "\n---\n".join(after)[:1500],
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--pattern", default=DEFAULT_PATTERN)
    ap.add_argument("--exclude-session", action="append", default=[])
    ap.add_argument("--rows", help="a JSONL file of extract-session-text.py rows, instead of reading transcripts")
    args = ap.parse_args()
    n = 0
    for p in pair(load_rows(args), args.pattern):
        print(json.dumps(p, ensure_ascii=False))
        n += 1
    print(f"{n} prompts paired", file=sys.stderr)


if __name__ == "__main__":
    main()
