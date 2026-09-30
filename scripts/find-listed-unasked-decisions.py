#!/usr/bin/env python3
# DESC: Find assistant replies that listed open decisions instead of asking them via AskUserQuestion
"""find-listed-unasked-decisions: survey transcripts for turns where the
assistant left decisions for the user in prose or a table instead of asking
them with AskUserQuestion, the failure /ask-open-decisions exists to fix.

Three modes:

  candidates  One row per human-prompted turn whose final reply did not call
              AskUserQuestion and either answered /outstanding or is long and
              uses decision language ("your call", "want me to", ...). Writes
              batch files ready for small-model classification: each case
              holds the prompt, the final reply, and the user's next message.
  asks        The user's own prompts asking to be asked ("ask me the
              questions", "AskUserQuestion", "wall of text"). Direct evidence,
              no classifier needed.
  aggregate   Merge classifier verdicts (JSONL, one object per case with at
              least "id" and "verdict") back onto the case metadata and print
              counts by /outstanding vs elsewhere, project, and follow-up.

Transcripts are found through claude_dirs.config_dirs() (~/.claude* plus
CLAUDE_CONFIG_DIR). First run 2026-09-30: 637 candidates, ~226 flagged
POSITIVE by Haiku (~8/10 precision on a spot check), 13 explicit asks.
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from claude_dirs import config_dirs  # noqa: E402

DECISION_RE = re.compile(
    r"(open (question|decision)|decision|needs? (you|your)|your call|up to you|want me to|"
    r"should I\b|shall I\b|do you want|would you like|let me know|say the word|"
    r"which (one|option|do you)|pick one|option [AB12]\b|awaiting|blocked on|you decide|\?\s*$)",
    re.I | re.M,
)
ASK_RE = re.compile(
    r"(ask ?user ?question|ask me (the|these|those) question|ask me the open|use the (ask|question) tool|"
    r"ask me instead|ask them to me|hard to (parse|read)|wall of text|say what am i deciding)",
    re.I,
)
CASE_RE = re.compile(r"======== CASE (\d+) \| (\S+) \| (\S+) \| session (\S+) \| outstanding=(\w+)")


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def is_human(e):
    if e.get("type") != "user" or e.get("isSidechain") or e.get("isMeta"):
        return False
    if (e.get("origin") or {}).get("kind") != "human":
        return False
    content = e["message"]["content"]
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    return not text_of(content).startswith(("<task-notification", "<local-command", "[Request interrupted"))


def transcripts():
    for cfg in config_dirs():
        for path in sorted(glob.glob(f"{cfg}/projects/*/*.jsonl")):
            project = os.path.basename(os.path.dirname(path))
            project = re.sub(r"^-Users-[^-]+-dev-?", "", project) or "dev"
            try:
                with open(path) as f:
                    yield project, [json.loads(line) for line in f]
            except (OSError, json.JSONDecodeError):
                continue


def turns(entries):
    """(prompt entry, final assistant text, asked?, next human text) per human turn."""
    humans = [i for i, e in enumerate(entries) if is_human(e)]
    for k, i in enumerate(humans):
        end = humans[k + 1] if k + 1 < len(humans) else len(entries)
        final, asked = None, False
        for e in entries[i + 1:end]:
            if e.get("type") != "assistant" or e.get("isSidechain"):
                continue
            for b in e["message"].get("content", []):
                if b.get("type") == "text":
                    final = b["text"]
                elif b.get("type") == "tool_use" and b["name"] == "AskUserQuestion":
                    asked = True
        nxt = text_of(entries[end]["message"]["content"]) if end < len(entries) else "(session ended)"
        yield entries[i], final, asked, nxt


def cmd_candidates(args):
    cases = []
    for project, entries in transcripts():
        for prompt_e, final, asked, nxt in turns(entries):
            if not final or asked:
                continue
            prompt = text_of(prompt_e["message"]["content"])
            outstanding = "<command-name>/outstanding" in prompt
            if not outstanding and not (len(final) >= args.min_chars and DECISION_RE.search(final)):
                continue
            cases.append((prompt_e["timestamp"], project, prompt_e["sessionId"], outstanding, prompt, final, nxt))
    cases.sort()
    os.makedirs(args.out_dir, exist_ok=True)
    per = -(-len(cases) // args.batches) if cases else 0
    for b in range(args.batches):
        chunk = cases[b * per:(b + 1) * per]
        if not chunk:
            continue
        with open(os.path.join(args.out_dir, f"batch{b:02d}.md"), "w") as out:
            for n, (ts, project, sid, outstanding, prompt, final, nxt) in enumerate(chunk):
                out.write(
                    f"\n\n======== CASE {b * per + n + 1:04d} | {project} | {ts} | session {sid} | outstanding={outstanding} ========\n"
                    f"### USER PROMPT\n{prompt[:500]}\n"
                    f"### ASSISTANT FINAL REPLY (AskUserQuestion NOT called this turn)\n{final}\n"
                    f"### USER'S NEXT MESSAGE\n{nxt[:1200]}\n"
                )
    print(f"{len(cases)} candidates, {per} per batch, written to {args.out_dir}")


def cmd_asks(args):
    for project, entries in transcripts():
        for e in entries:
            if not is_human(e):
                continue
            t = text_of(e["message"]["content"])
            if t.startswith("<") or not ASK_RE.search(t):
                continue
            flat = re.sub(r"\s+", " ", t)
            print(f"{e['timestamp'][:10]}  {project[:24]:24}  {flat[:160]}")


def cmd_aggregate(args):
    meta = {}
    for path in glob.glob(os.path.join(args.batch_dir, "batch*.md")):
        with open(path) as f:
            for m in CASE_RE.finditer(f.read()):
                meta[m[1]] = dict(project=m[2], ts=m[3], session=m[4], outstanding=m[5] == "True")
    verdicts = []
    for path in sorted(glob.glob(os.path.join(args.verdict_dir, "*.jsonl"))):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    v = json.loads(line)
                    v.update(meta.get(v["id"], {}))
                    verdicts.append(v)
    print(f"{len(verdicts)} verdicts for {len(meta)} cases")
    print("by /outstanding, verdict:", dict(collections.Counter((v.get("outstanding"), v["verdict"]) for v in verdicts)))
    pos = [v for v in verdicts if v["verdict"] == "POSITIVE"]
    if not pos:
        return
    print("positive sessions:", len({v.get("session") for v in pos}))
    print("positive by project:", collections.Counter(v.get("project") for v in pos).most_common(10))
    print("user follow-up:", dict(collections.Counter(v.get("user_followup") for v in pos)))
    numbered = [v for v in pos if re.match(r"\s*(1[-.)]|#?1\b)", v.get("followup_quote", ""))]
    print("next message answers by number:", len(numbered))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidates", help="write candidate turns as batch files for classification")
    c.add_argument("--out-dir", required=True)
    c.add_argument("--batches", type=int, default=10)
    c.add_argument("--min-chars", type=int, default=800, help="minimum reply length outside /outstanding")
    sub.add_parser("asks", help="print the user's own requests to be asked")
    a = sub.add_parser("aggregate", help="summarise classifier verdicts")
    a.add_argument("--batch-dir", required=True)
    a.add_argument("--verdict-dir", required=True)
    args = ap.parse_args()
    {"candidates": cmd_candidates, "asks": cmd_asks, "aggregate": cmd_aggregate}[args.cmd](args)


if __name__ == "__main__":
    main()
