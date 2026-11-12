#!/usr/bin/env python3
# DESC: Survey what the idle-end Stop hook did: outcomes of every refusal, and typed nudges before and after it existed
"""Survey hooks/refuse-idle-end-of-turn.sh from the chat logs.

Prints, over the last N days of transcripts (read only through extract-session-text.py):
  1. every "Stop hook feedback" refusal, what the agent did next (asked, worked, wrote a bare "Nothing left",
     ended with text only), how a forced question ended (answered or rejected), and the split by whether the
     turn made any tool call;
  2. typed nudges ("continue", "why did you stop", ...) and typed /ask-open-decisions per active day before and
     after the hook was added (the date of the hook's first commit, or --hook-date).

Counts are regex estimates. Read about eight episodes in context (extract-session-text.py --around) before
drawing a verdict. Usage: survey-stop-hook-refusals.py [--days 40] [--hook-date YYYY-MM-DD] [--exclude-session ID]
"""
import argparse, collections, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READER = ROOT / "scripts" / "extract-session-text.py"
HOOK = "hooks/refuse-idle-end-of-turn.sh"
QUESTION = re.compile(r"\?|^\s*(why|what|how|where|when|who|which|is|are|do|does|did|can|could|would|should|will)\b", re.I)
NUDGE = re.compile(r"(?i)^\s*(continue|lets continue|let's continue|okay lets continue|ok lets continue|proceed|keep going|go on|next unit|why did you stop|why have you stopped|why you stopped|why stop|why are you stopping|what now)\W*$|why (did|have) you (stop|stopped)|you stopped|dont stop|don't stop")
REJECTED = re.compile(r"(?i)doesn.t want to proceed|tool use was rejected")


def rows_of(args: list[str]) -> list[dict]:
    p = subprocess.run([sys.executable, str(READER), *args, "--json"], capture_output=True, text=True)
    rows = []
    for line in p.stdout.splitlines():
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row.get("sidechain"):
            rows.append(row)
    return rows


def human(r: dict) -> bool:
    t = r.get("text") or ""
    return r.get("group") == "user" and r.get("origin") == "human" and not r.get("meta") and not t.startswith("[Request interrupted")


def refusal(r: dict) -> bool:
    return r.get("group") == "user" and bool(r.get("meta")) and (r.get("text") or "").startswith("Stop hook feedback")


def episodes(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        if not refusal(r):
            continue
        k = i - 1
        while k >= 0 and not human(rows[k]):
            k -= 1
        ncalls = sum(1 for x in rows[k + 1:i] if (x.get("label") or "").startswith("CALL"))
        after = []
        for x in rows[i + 1:]:
            if human(x) or refusal(x):
                break
            after.append(x)
        labels = [x.get("label") or "" for x in after]
        if "ASK" in labels:
            res = next((y.get("text") or "" for y in after[labels.index("ASK") + 1:] if (y.get("label") or "").startswith("RESULT")), "")
            first = "ask-rejected" if REJECTED.search(res) else ("ask-answered" if "been answered" in res[:60] or res.startswith("The user answered") else "ask-other")
        elif any(l.startswith("CALL") for l in labels):
            first = "work"
        elif re.search(r"Nothing left", " ".join(x.get("text") or "" for x in after if x.get("label") == "ASSISTANT")):
            first = "nothing-left"
        else:
            first = "text-only"
        kind = "idle" if "ending the turn idle" in r["text"] else ("prose-offer" if "offering work" in r["text"] else "other")
        out.append({"time": r["time"], "kind": kind, "first": first, "tool_calls_in_turn": ncalls,
                    "opened_by_question": bool(k >= 0 and QUESTION.search((rows[k].get("text") or "")[:300]))})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=40)
    ap.add_argument("--hook-date", help="first day the hook existed (default: date of the hook's first commit)")
    ap.add_argument("--exclude-session", default="", help="a session to leave out, normally this one")
    a = ap.parse_args()
    hook_date = a.hook_date or subprocess.run(
        ["git", "-C", str(ROOT), "log", "--diff-filter=A", "--format=%ad", "--date=short", "--", HOOK],
        capture_output=True, text=True).stdout.split()[-1]
    base = ["--all", "--days", str(a.days)] + (["--exclude-session", a.exclude_session] if a.exclude_session else [])
    win = subprocess.run([sys.executable, str(READER), "--all", "--days", str(a.days), "--window"], capture_output=True, text=True).stdout.strip()
    print(f"window: {win}\nhook added: {hook_date}\n")

    hits = rows_of(base + ["--kinds", "user", "--max-chars", "200", "--grep", "Stop hook feedback"])
    sessions = sorted({r["session"] for r in hits if refusal(r)})
    eps = []
    for s in sessions:
        eps += episodes(rows_of([s, "--kinds", "user,assistant,agents,calls", "--max-chars", "600"]))
    print(f"{len(eps)} refusals in {len(sessions)} sessions")
    for k, v in collections.Counter((e["kind"], e["first"]) for e in eps).most_common():
        print(f"  {v:4d}  {k[0]:11s} -> {k[1]}")
    print("\nidle-end refusals by whether the turn made a tool call:")
    for tier, test in (("no tool call", lambda e: e["tool_calls_in_turn"] == 0), ("tool calls", lambda e: e["tool_calls_in_turn"] > 0)):
        sel = [e for e in eps if e["kind"] == "idle" and test(e)]
        print(f"  {tier}: {len(sel)}  {dict(collections.Counter(e['first'] for e in sel))}")

    prompts = [r for r in rows_of(base + ["--kinds", "user", "--max-chars", "300"]) if human(r)]
    per_day = collections.defaultdict(lambda: [0, 0, 0])
    for r in prompts:
        d = per_day[r["time"][:10]]
        d[0] += 1
        d[1] += bool(NUDGE.search((r.get("text") or "")[:200]))
        d[2] += "ask-open-decisions" in (r.get("text") or "")
    print("\ntyped nudges and /ask-open-decisions per active day (days with 20+ prompts):")
    for name, keep in (("before", lambda d: d < hook_date), ("after", lambda d: d >= hook_date)):
        days = [d for d in per_day if keep(d) and per_day[d][0] >= 20]
        if days:
            n, ao = sum(per_day[d][1] for d in days), sum(per_day[d][2] for d in days)
            print(f"  {name}: {len(days)} days, nudges {n} ({n / len(days):.1f}/day), /ask-open-decisions {ao} ({ao / len(days):.1f}/day)")


if __name__ == "__main__":
    main()
