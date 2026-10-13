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
from transcript_items import items, transcripts as transcript_files  # noqa: E402

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


RESULT_LABELS = ("RESULT ", "TOOL-RESULT ")
QUEUE_LABELS = ("RECAP", "USER(queued)")
OTHER_ASSISTANT_LABELS = ("AGENT-SPAWN", "SENDMSG")


def entries(path, project):
    """One record per user/assistant entry of a transcript, built from its items:
    kind, time, session, sidechain, meta, origin, text (user text blocks joined
    by newline), has_result (a tool_result block), final (last assistant text),
    asked (an AskUserQuestion call)."""
    cur = None
    for it in items(path, project, want={"user", "assistant", "agents", "tools"}):
        label = it["label"]
        if label in QUEUE_LABELS:
            continue
        if cur is None or cur["line"] != it["line"]:
            if cur:
                yield cur
            cur = {k: it[k] for k in ("line", "time", "session", "sidechain", "meta", "origin")}
            cur.update(kind="assistant", texts=[], has_result=False, final=None, asked=False)
        if label == "ASSISTANT":
            cur["final"] = it["text"]
        elif label == "ASK":
            cur["asked"] = True
        elif label in OTHER_ASSISTANT_LABELS:
            pass
        else:
            cur["kind"] = "user"
            if label.startswith(RESULT_LABELS):
                cur["has_result"] = True
            else:
                cur["texts"].append(it["text"])
    if cur:
        yield cur


def is_human(e):
    if e["kind"] != "user" or e["sidechain"] or e["meta"] or e["origin"] != "human" or e["has_result"]:
        return False
    return not "\n".join(e["texts"]).startswith(("<task-notification", "<local-command", "[Request interrupted"))


def transcripts():
    for path, _, _ in transcript_files():
        project = os.path.basename(os.path.dirname(path))
        project = re.sub(r"^-Users-[^-]+-dev-?", "", project) or "dev"
        try:
            yield project, list(entries(path, project))
        except OSError:
            continue


def turns(entries):
    """(prompt entry, final assistant text, asked?, next human text) per human turn."""
    humans = [i for i, e in enumerate(entries) if is_human(e)]
    for k, i in enumerate(humans):
        end = humans[k + 1] if k + 1 < len(humans) else len(entries)
        final, asked = None, False
        for e in entries[i + 1:end]:
            if e["kind"] != "assistant" or e["sidechain"]:
                continue
            if e["final"] is not None:
                final = e["final"]
            asked = asked or e["asked"]
        nxt = "\n".join(entries[end]["texts"]) if end < len(entries) else "(session ended)"
        yield entries[i], final, asked, nxt


def cmd_candidates(args):
    cases = []
    for project, entries in transcripts():
        for prompt_e, final, asked, nxt in turns(entries):
            if not final or asked:
                continue
            prompt = "\n".join(prompt_e["texts"])
            outstanding = "<command-name>/outstanding" in prompt
            if not outstanding and not (len(final) >= args.min_chars and DECISION_RE.search(final)):
                continue
            cases.append((prompt_e["time"], project, prompt_e["session"], outstanding, prompt, final, nxt))
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
            t = "\n".join(e["texts"])
            if t.startswith("<") or not ASK_RE.search(t):
                continue
            flat = re.sub(r"\s+", " ", t)
            print(f"{e['time'][:10]}  {project[:24]:24}  {flat[:160]}")


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
