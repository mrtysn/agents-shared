#!/usr/bin/env python3
# DESC: Join system-one shadow-log verdict rows with their outcome rows and report per-hook agreement, or export a labelled cases TSV
"""
system-one-receipts: the logs label themselves (design doc section 13). Every
verdict row `system-one ask --hook` writes carries an "id"; a later hook call
appends an "outcome" row -- {"kind":"outcome","ref":<id>, ...} -- to the same
shadow/<hook>/<session>.jsonl once the real answer is known:

  prompt  hooks/system-one-prompt.sh, at the *next* prompt of the session:
          next_kind, next_is_command, acted (any assistant tool_use between
          the two prompts), tool_calls.
  stop    also written by the prompt hook, one per not-yet-labelled Stop row:
          next_prompt_kind, next_command, ran_outstanding -- receipt data for
          whatever the user did right after the reply, joined against the
          Stop hook's verdict (needless_table/overlong; will_run_outstanding
          was dropped from the model and is no longer a question here).
  bash    hooks/system-one-bash-post.sh (PostToolUse and PostToolUseFailure),
          matched by tool_use_id (state_sha256 for older rows): ran (always
          true when this row exists), exit_code (0 on PostToolUse; the N of
          "Exit code N" on PostToolUseFailure; null for a timeout/interrupt),
          failed, interrupted. A bash verdict row with no outcome row is read
          as "did not run" (denied, cancelled, or blocked by another guard).
  ask     no outcome mechanism exists yet (not built in this slice; see the
          README/notebook). Reported as zero rows, not fabricated.

This script never re-derives a threshold or re-runs the model: it only reads
what the hooks already decided (the verdict row's own would_act/fired) and
compares it with what the outcome row says actually happened.

Usage:
    scripts/system-one-receipts.py [--state-dir DIR] [--hook NAME]
    scripts/system-one-receipts.py --export-cases HOOK OUT.tsv [--state-dir DIR]

--state-dir defaults the same way scripts/system-one resolves it: the
SYSTEM_ONE_STATE_DIR environment variable, else the same key read from
${CLAUDE_CONFIG_DIR:-~/.claude}/system-one.local.sh, else
${XDG_STATE_HOME:-~/.local/state}/system-one. Nothing is hardcoded to one
machine's layout.

Real prompt/message text only ever appears in the file --export-cases is
told to write, chosen by the caller (defaults under --state-dir, never this
repo, when the caller gives a bare filename); the summary table prints
counts and rates only.

--export-cases writes the hooks/tests case-file shape for the hook: the
prompt and stop hooks log their full state (--keep-state since the review of
section 13), and the exporter splits that state back into the case file's
text columns (prompt/previous; message). A row logged before that, carrying
only the 80-character state_excerpt, is exported from the excerpt and marked
in a trailing comment column so it is never mistaken for full text.
"""
import argparse
import glob
import json
import os
import re
import sys


def resolve_state_dir(explicit):
    if explicit:
        return explicit
    env = os.environ.get("SYSTEM_ONE_STATE_DIR")
    if env:
        return env
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    config_file = os.path.join(config_dir, "system-one.local.sh")
    if os.path.isfile(config_file):
        try:
            with open(config_file, encoding="utf-8") as f:
                text = f.read()
            m = re.search(r'^\s*(?:export\s+)?SYSTEM_ONE_STATE_DIR\s*=\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
            if m:
                return os.path.expandvars(os.path.expanduser(m.group(1)))
        except OSError:
            pass
    xdg = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(xdg, "system-one")


HOOKS = ("bash", "prompt", "stop", "ask")


def load_hook_rows(shadow_dir, hook):
    """All rows for one hook across every session, split into verdict rows
    (keyed by id, when present) and outcome rows (kind == "outcome")."""
    verdicts = {}
    verdicts_no_id = []
    outcomes = []
    pattern = os.path.join(shadow_dir, hook, "*.jsonl")
    for path in sorted(glob.glob(pattern)):
        session = os.path.basename(path)[: -len(".jsonl")]
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, dict):
                        continue
                    row["_session"] = session
                    if row.get("kind") == "outcome":
                        outcomes.append(row)
                    else:
                        rid = row.get("id")
                        if rid:
                            verdicts[rid] = row
                        else:
                            verdicts_no_id.append(row)
        except OSError:
            continue
    return verdicts, verdicts_no_id, outcomes


def summarize_hook(hook, verdicts, verdicts_no_id, outcomes):
    n_verdict = len(verdicts) + len(verdicts_no_id)
    resolved = [(o, verdicts[o["ref"]]) for o in outcomes if o.get("ref") in verdicts]
    n_outcome = len(resolved)
    row = {
        "hook": hook,
        "rows": n_verdict,
        "with_outcome": n_outcome,
        "no_id": len(verdicts_no_id),
        "agreement_label": "-",
        "agreement": None,
        "agreement_n": 0,
    }
    if hook == "prompt":
        # Implied label: an order-kind prompt implies the agent should act;
        # question/wish/correction/other implies it should not. Agreement =
        # how often that implication matched what the outcome row recorded.
        n = 0
        hit = 0
        for o, v in resolved:
            kind = ((v.get("answers") or {}).get("kind") or {}).get("choice")
            acted = o.get("acted")
            if kind is None or not isinstance(acted, bool):
                continue
            n += 1
            implied = kind == "order"
            hit += implied == acted
        row["agreement_label"] = "kind==order implies acted"
        row["agreement"] = (hit / n) if n else None
        row["agreement_n"] = n
    elif hook == "stop":
        # Generic, question-agnostic: did the verdict fire at all (either
        # needless_table or overlong, the Stop hook's two live questions --
        # will_run_outstanding was dropped from the model, so this no longer
        # names a specific question) vs whether the user actually typed a
        # follow-up command in response. next_command/ran_outstanding are
        # still valid receipt data from stop-outcome; only the
        # question-specific agreement metric they used to feed is gone.
        n = 0
        hit = 0
        for o, v in resolved:
            fired = v.get("fired") or []
            predicted = bool(fired)
            actual = o.get("next_command")
            if actual is None:
                continue
            actual = bool(actual)
            n += 1
            hit += predicted == actual
        row["agreement_label"] = "verdict fired vs next_command"
        row["agreement"] = (hit / n) if n else None
        row["agreement_n"] = n
    elif hook == "bash":
        # ran = an outcome row exists at all for this verdict row (bash-post
        # only ever logs one when the command actually ran). A verdict row
        # with no matching outcome reads as "did not run". Agreement: the
        # gate would have asked and the command did not run (something else
        # refused it), or it would not have asked and the command ran. Rough,
        # since an approved ask also runs; the label says so.
        outcome_refs = {o["ref"] for o in outcomes if o.get("ref")}
        n = 0
        hit = 0
        for vid, v in verdicts.items():
            would_act = v.get("would_act")
            if not isinstance(would_act, bool):
                continue
            ran = vid in outcome_refs
            n += 1
            hit += would_act != ran
        failed = sum(1 for o, _ in resolved if o.get("failed") is True)
        row["agreement_label"] = f"would_act (ask-fires) vs did-not-run; {failed} ran and failed"
        row["agreement"] = (hit / n) if n else None
        row["agreement_n"] = n
    return row


def print_summary(rows, verbose_no_outcomes):
    header = f"{'hook':<8} {'rows':>7} {'w/outcome':>10} {'agreement':>10} {'n':>6}  label"
    print(header)
    print("-" * len(header))
    any_outcomes = False
    for r in rows:
        any_outcomes = any_outcomes or r["with_outcome"] > 0
        agr = f"{r['agreement']:.2f}" if r["agreement"] is not None else "-"
        print(f"{r['hook']:<8} {r['rows']:>7} {r['with_outcome']:>10} {agr:>10} {r['agreement_n']:>6}  {r['agreement_label']}")
    if not any_outcomes:
        print()
        print("no outcome rows anywhere under this state dir yet (expected on a log with no")
        print("prompt-hook/bash-post traffic since the receipts change shipped) -- every row")
        print("above with_outcome=0 is honest, not a bug.")


PROMPT_HEADER = "kind\twants_action\tprompt\tprevious"
STOP_HEADER = "label\tmessage"


def tsv_text(text):
    """One case-file cell: tabs to spaces, newlines to a literal backslash-n
    (the readers unescape), same as the hand-labelled files."""
    return (text or "").replace("\t", " ").replace("\r", "").replace("\n", "\\n")


def split_prompt_state(state):
    """Inverse of hooks/system-one-prompt.sh's STATE: "prompt:\n<prompt>" plus
    an optional "\nprevious:\n<excerpt>". Returns (prompt, previous)."""
    if not state.startswith("prompt:\n"):
        return state, ""
    body = state[len("prompt:\n"):]
    head, sep, tail = body.partition("\nprevious:\n")
    return (head, tail) if sep else (body, "")


def split_stop_state(state):
    """Inverse of hooks/system-one-stop.sh's STATE: "assistant message:\n<excerpt>
    \nlength_chars: N  tables: N  headers: N  bullets: N". Returns the
    excerpt (message_chars of the message, the case file's text column)."""
    if not state.startswith("assistant message:\n"):
        return state
    body = state[len("assistant message:\n"):]
    head, sep, _ = body.rpartition("\nlength_chars: ")
    return head if sep else body


def state_text(row):
    """(text, full) -- the logged state and whether it is the full state or
    only the 80-character excerpt of a pre-review row."""
    if row.get("state") is not None:
        return row["state"], True
    return row.get("state_excerpt") or "", False


def export_prompt_cases(verdicts, outcomes, out_path):
    """kind: the verdict's own predicted argmax (best-effort -- the outcome
    row does not independently re-grade the referenced prompt's kind, only
    whether the agent acted). wants_action: outcome.acted, a genuine label
    (0/1). prompt/previous: split from the logged full state (the prompt cut
    to state.prompt_chars, the previous: excerpt when the hook had one),
    exactly the columns hooks/tests/system-one-prompt-cases.tsv carries. A
    pre-review row with only state_excerpt gets a fifth column
    "excerpt-only" so it can be filtered out."""
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("# " + PROMPT_HEADER + "\n")
        out.write(
            "# Exported by scripts/system-one-receipts.py from outcome rows. kind is the "
            "verdict's own prediction (not independently verified by the outcome); "
            "wants_action is outcome.acted, a genuine label. prompt/previous are the "
            "full state the hook sent; a row marked excerpt-only in a fifth column "
            "predates full-state logging and carries 80 characters.\n"
        )
        for o in outcomes:
            v = verdicts.get(o.get("ref"))
            if not v:
                continue
            kind = ((v.get("answers") or {}).get("kind") or {}).get("choice") or ""
            acted = o.get("acted")
            if not kind or not isinstance(acted, bool):
                continue
            state, full = state_text(v)
            prompt, previous = split_prompt_state(state)
            mark = "" if full else "\texcerpt-only"
            out.write(f"{kind}\t{int(acted)}\t{tsv_text(prompt)}\t{tsv_text(previous)}{mark}\n")
            n += 1
    return n


def export_stop_cases(verdicts, outcomes, out_path):
    """The existing hooks/tests/system-one-stop-cases.tsv label column is
    padded/fitting (the answer-shape question, needless_table/overlong) --
    a different signal from ran_outstanding, which stop-outcome labels (the
    /outstanding question this dropped model's will_run_outstanding question
    used to score; ran_outstanding itself is still genuine receipt data,
    only the model question is gone). There is no cases file for that signal
    yet, so this reuses the stop-cases file's two-column shape with the
    label column carrying ran_outstanding instead, called out by name in the
    header comment so it is never silently merged as if it were a
    padded/fitting label."""
    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        out.write("# " + STOP_HEADER + "\n")
        out.write(
            "# Exported by scripts/system-one-receipts.py. label here is ran_outstanding "
            "(outstanding/not_outstanding) from stop-outcome, NOT the padded/fitting label "
            "hooks/tests/system-one-stop-cases.tsv otherwise carries -- do not concatenate "
            "with that file without relabelling this column. message is the assistant "
            "message excerpt from the logged full state (message_chars, 1500 by default); "
            "a row marked excerpt-only in a third column predates full-state logging and "
            "carries 80 characters. The Stop hook logs one verdict row per Stop "
            "(needless_table + overlong in a single call); a session that also carries "
            "older two-row-per-Stop logs (predating that merge) exports both, so dedupe "
            "on message if that matters.\n"
        )
        for o in outcomes:
            v = verdicts.get(o.get("ref"))
            if not v:
                continue
            actual = o.get("ran_outstanding")
            if not isinstance(actual, bool):
                continue
            label = "outstanding" if actual else "not_outstanding"
            state, full = state_text(v)
            mark = "" if full else "\texcerpt-only"
            out.write(f"{label}\t{tsv_text(split_stop_state(state))}{mark}\n")
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", help="system-one state dir (default: resolved like scripts/system-one)")
    ap.add_argument("--hook", choices=HOOKS, help="restrict the summary to one hook")
    ap.add_argument(
        "--export-cases",
        nargs=2,
        metavar=("HOOK", "OUT.tsv"),
        help="write a labelled cases TSV for HOOK (prompt or stop; bash and ask have no "
        "outcome-derived gold label yet and export zero rows)",
    )
    args = ap.parse_args()

    state_dir = resolve_state_dir(args.state_dir)
    shadow_dir = os.path.join(state_dir, "shadow")
    if not os.path.isdir(shadow_dir):
        print(f"system-one-receipts: no shadow log under {shadow_dir}", file=sys.stderr)
        return 1

    if args.export_cases:
        hook, out_path = args.export_cases
        if hook not in HOOKS:
            print(f"system-one-receipts: unknown hook {hook!r}", file=sys.stderr)
            return 1
        verdicts, _, outcomes = load_hook_rows(shadow_dir, hook)
        if hook == "prompt":
            n = export_prompt_cases(verdicts, outcomes, out_path)
        elif hook == "stop":
            n = export_stop_cases(verdicts, outcomes, out_path)
        else:
            with open(out_path, "w", encoding="utf-8") as out:
                out.write(f"# no outcome-derived gold label exists yet for hook={hook}; 0 rows.\n")
            n = 0
        print(f"wrote {n} row(s) to {out_path}")
        return 0

    hooks = [args.hook] if args.hook else list(HOOKS)
    rows = []
    for hook in hooks:
        verdicts, verdicts_no_id, outcomes = load_hook_rows(shadow_dir, hook)
        rows.append(summarize_hook(hook, verdicts, verdicts_no_id, outcomes))
    print_summary(rows, verbose_no_outcomes=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
