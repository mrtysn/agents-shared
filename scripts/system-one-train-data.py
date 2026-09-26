#!/usr/bin/env python3
# DESC: Build the system-one fine-tune JSONL (bash/prompt/stop/ask cases plus /outstanding stop moments) and its train/val/test splits
"""
system-one-train-data: build one JSONL fine-tune dataset for the four system-one
hooks (bash, prompt, stop, ask) plus the /outstanding Stop-moment classifier, from
the existing hand-labelled case files and, for /outstanding, a fresh
command-moments-survey.py pass over local transcripts.

Every row is one (state, question, target) training item:
    {"task", "split", "row_id", "state", "question", "target", "label"}

`question` is Laya's internal question shape ({"t", "ins", "crit"}, built with
laya.Agent._to_internal from the same hook questions.json the hooks and
scripts/system-one-measure.py already read) so system-one-train.py can hand it
straight to laya.common.build_sequence. `target` is a one-hot list of floats in
the exact option order laya.common.render_options produces for that question, so
it lines up with the marker positions build_sequence emits.

`state` is built with the exact same helpers system-one-measure.py uses to score
the hooks (build_prompt_state / build_stop_state / normalise / ask_state, loaded
from that script so the two can never drift), with each hook's file defaults:
  bash:   cwd+command state, foreign_process/irreversible/leaves_machine, 106 rows x 3 q
  prompt: prompt state (previous off, prompt cap 600), kind + wants_action, 324 rows x 2 q
  stop:   assistant-message state (message cap 1500), needless_table only, 184 rows x 1 q
          (gold is the file's single fitting/padded column: padded -> needless_table=true)
  ask:    one call per question, answered_in_context/routine_default/naming_or_irreversible,
          200 rows x 1 q (three questions total across the file's rows)

/outstanding is built from scripts/command-moments-survey.py --commands outstanding
(run fresh into --out-dir/survey), a noul question asking whether the user will run
/outstanding next, over exactly the state hooks/system-one-stop.sh would send at that
Stop: build_stop_state(row["last_text_full"], state.message_chars from
hooks/system-one-stop-questions.json) -- the message's head excerpt plus the
length/tables/headers/bullets line counted over the whole message. (The survey's
"last_text" field is the message's last 1500 characters, the wrong end; the survey
stores the full text as "last_text_full" for this.) Nothing from the labelling prompt
itself (next_prompt / next_slash) enters the state. Negatives (every non-"outstanding"
label: other/intermediate/session_end) are downsampled to --neg-ratio times the
positive count (default 4), with all positives kept; the sample is drawn with
Python's random module seeded by --seed, so it is reproducible but never the same
rows as a different --seed. This task's rows are real session text, so its JSONL and
splits never go in the repo -- both files default under $XDG_STATE_HOME (or
~/.local/state).

Splits: per task, 20% held out as test (stratified by a per-task label: bash's
target class, prompt/stop's gold class, ask's any-of-3-positive flag, outstanding's
positive/negative flag), then 20% of the remainder as val, with a fixed --seed
(default 0). row_id is the 0-based index of the case row within its source file
after blank/comment lines are stripped (ask/bash/prompt/stop: the same order
scripts/system-one-measure.py's loaders hand back, so --splits/--split there scores
exactly these rows; outstanding: the 0-based index in the downsampled row list this
script writes to --out-dir/outstanding_rows.jsonl). splits.json holds
{task: {split: [row_id, ...]}}.

Runs fully offline: HF_HUB_OFFLINE=1 is set before laya is imported. Needs no model
weights -- only laya.Agent._to_internal (a staticmethod) and laya.common.render_options.

Usage:
    system-one-train-data.py [--out-dir DIR] [--seed N] [--neg-ratio N]
                              [--skip-outstanding] [--agents-shared DIR]
"""
import argparse
import importlib.util
import json
import os
import random
import subprocess
import sys

DEFAULT_OUT_DIR = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
                               "system-one", "train")


def default_agents_shared() -> str:
    """agents-shared repo root, derived from this script's own location (scripts/<this file>)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def load_measure_module(agents_shared: str):
    """Import scripts/system-one-measure.py by path (its name has hyphens, so a plain
    `import` cannot reach it) to reuse its state builders and case loaders verbatim."""
    path = os.path.join(agents_shared, "scripts", "system-one-measure.py")
    spec = importlib.util.spec_from_file_location("system_one_measure", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def to_internal(qdef: dict) -> dict:
    import laya
    return laya.Agent._to_internal(qdef)


def one_hot(n: int, i: int) -> list:
    v = [0.0] * n
    v[i] = 1.0
    return v


def noul_target(is_true: bool) -> list:
    return [0.0, 1.0] if is_true else [1.0, 0.0]


def stratified_split(ids_by_label: dict, seed: int) -> dict:
    """20% test per stratum, then 20% of the rest as val, shuffled with a fresh
    random.Random(seed) per stratum so the split is deterministic and does not
    depend on dict/label iteration order."""
    train, val, test = [], [], []
    for label in sorted(ids_by_label):
        ids = sorted(ids_by_label[label])
        random.Random(seed).shuffle(ids)
        n_test = round(0.2 * len(ids))
        test_ids, rest = ids[:n_test], ids[n_test:]
        n_val = round(0.2 * len(rest))
        val_ids, train_ids = rest[:n_val], rest[n_val:]
        test += test_ids
        val += val_ids
        train += train_ids
    return {"train": sorted(train), "val": sorted(val), "test": sorted(test)}


# --------------------------------------------------------------------------- bash

def build_bash_items(m, agents_shared: str):
    qfile = os.path.join(agents_shared, "hooks", "system-one-bash-questions.json")
    cfile = os.path.join(agents_shared, "hooks", "tests", "system-one-bash-cases.tsv")
    with open(qfile, encoding="utf-8") as f:
        doc = json.load(f)
    keep = int(doc.get("state", {}).get("heredoc_keep", 0))
    rows = m.load_cases(cfile)
    qs = {k: to_internal(doc["questions"][k]) for k in ("foreign_process", "irreversible", "leaves_machine")}
    items, strat = [], {}
    for row_id, (cmd, label) in enumerate(rows):
        state = f"cwd: {m.CWD}\ncommand:\n{m.normalise(cmd, keep)}"
        strat.setdefault(label["target"], []).append(row_id)
        for qname, q in qs.items():
            is_true = label[qname] >= 1
            items.append({"task": "bash", "row_id": row_id, "state": state, "question": q,
                          "target": noul_target(is_true), "label": "true" if is_true else "false",
                          "question_name": qname})
    return items, strat


# ------------------------------------------------------------------------- prompt

def build_prompt_items(m, agents_shared: str):
    qfile = os.path.join(agents_shared, "hooks", "system-one-prompt-questions.json")
    cfile = os.path.join(agents_shared, "hooks", "tests", "system-one-prompt-cases.tsv")
    with open(qfile, encoding="utf-8") as f:
        doc = json.load(f)
    state_opts = doc.get("state", {})
    prompt_chars = int(state_opts.get("prompt_chars", 600))
    previous_chars = int(state_opts.get("previous_chars", 0))
    kind_q = to_internal(doc["questions"]["kind"])
    kind_keys = list(doc["questions"]["kind"]["criteria"].keys())
    action_q = to_internal(doc["questions"]["wants_action"])

    rows = []
    with open(cfile, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 3:
                continue
            rows.append({"gold": fields[0], "wants_action": fields[1], "text": fields[2],
                        "prev": m.unescape_nl(fields[3]) if len(fields) > 3 else ""})

    items, strat = [], {}
    for row_id, r in enumerate(rows):
        state = m.build_prompt_state(r["text"], r["prev"], prompt_chars, previous_chars)
        strat.setdefault(r["gold"], []).append(row_id)
        items.append({"task": "prompt", "row_id": row_id, "state": state, "question": kind_q,
                      "target": one_hot(len(kind_keys), kind_keys.index(r["gold"])), "label": r["gold"],
                      "question_name": "kind"})
        wants = r["wants_action"] == "1"
        items.append({"task": "prompt", "row_id": row_id, "state": state, "question": action_q,
                      "target": noul_target(wants), "label": "true" if wants else "false",
                      "question_name": "wants_action"})
    return items, strat


# --------------------------------------------------------------------------- stop

def build_stop_items(m, agents_shared: str):
    qfile = os.path.join(agents_shared, "hooks", "system-one-stop-questions.json")
    cfile = os.path.join(agents_shared, "hooks", "tests", "system-one-stop-cases.tsv")
    with open(qfile, encoding="utf-8") as f:
        doc = json.load(f)
    message_chars = int(doc.get("state", {}).get("message_chars", 1500))
    q = to_internal(doc["questions"]["needless_table"])

    rows = []
    with open(cfile, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            rows.append({"gold": fields[0], "text": m.unescape_nl("\t".join(fields[1:]))})

    items, strat = [], {}
    for row_id, r in enumerate(rows):
        state = m.build_stop_state(r["text"], message_chars)
        is_padded = r["gold"] == "padded"
        strat.setdefault(r["gold"], []).append(row_id)
        items.append({"task": "stop", "row_id": row_id, "state": state, "question": q,
                      "target": noul_target(is_padded), "label": "true" if is_padded else "false",
                      "question_name": "needless_table"})
    return items, strat


# ---------------------------------------------------------------------------- ask

ASK_QUESTION_KEYS = ("answered_in_context", "routine_default", "naming_or_irreversible")


def build_ask_items(m, agents_shared: str):
    qfile = os.path.join(agents_shared, "hooks", "system-one-ask-questions.json")
    cfile = os.path.join(agents_shared, "hooks", "tests", "system-one-ask-cases.tsv")
    with open(qfile, encoding="utf-8") as f:
        doc = json.load(f)
    state_opts = doc.get("state", {})
    recent_chars = int(state_opts.get("recent_chars", 150))
    recent_prompts = int(state_opts.get("recent_prompts", 0))
    desc_chars = int(state_opts.get("description_chars", 50))
    qs = {k: to_internal(doc["questions"][k]) for k in ASK_QUESTION_KEYS}

    rows = m.ask_load_cases(cfile)
    items, strat = [], {}
    for row_id, r in enumerate(rows):
        state = m.ask_state([r["question"]], m.ask_recent_block(r["recent"], recent_prompts, recent_chars), desc_chars)
        strat.setdefault(str(any(r["gold"][k] >= 1 for k in ASK_QUESTION_KEYS)), []).append(row_id)
        for qname, q in qs.items():
            is_true = r["gold"][qname] >= 1
            items.append({"task": "ask", "row_id": row_id, "state": state, "question": q,
                          "target": noul_target(is_true), "label": "true" if is_true else "false",
                          "question_name": qname})
    return items, strat


# ----------------------------------------------------------------------- outstanding

OUTSTANDING_QUESTION = {
    "type": "noul",
    "instructions": "Will the user's next typed message run the /outstanding slash command "
                    "(asking to recap what got done in the session, what's left, and where "
                    "each item stands), rather than something else?",
}


def build_outstanding_items(m, agents_shared: str, out_dir: str, seed: int, neg_ratio: float, python_bin: str):
    survey = os.path.join(agents_shared, "scripts", "command-moments-survey.py")
    survey_dir = os.path.join(out_dir, "survey")
    os.makedirs(survey_dir, exist_ok=True)
    rows_path = os.path.join(survey_dir, "command_moments_rows.jsonl")
    print(f"[outstanding] running {survey} --commands outstanding --out-dir {survey_dir}", file=sys.stderr)
    subprocess.run([python_bin, survey, "--commands", "outstanding", "--out-dir", survey_dir], check=True)

    # The Stop hook's own excerpt length, from the single source the hook reads.
    with open(os.path.join(agents_shared, "hooks", "system-one-stop-questions.json"), encoding="utf-8") as f:
        message_chars = int(json.load(f).get("state", {}).get("message_chars", 1500))

    all_rows = []
    with open(rows_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_rows.append(json.loads(line))
    if all_rows and "last_text_full" not in all_rows[0]:
        sys.exit(f"{rows_path}: rows carry no last_text_full; command-moments-survey.py is out of date")

    positives = [r for r in all_rows if r["label"] == "outstanding"]
    negatives = [r for r in all_rows if r["label"] != "outstanding"]
    n_neg = min(len(negatives), round(neg_ratio * len(positives)))
    sampled_neg = random.Random(seed).sample(negatives, n_neg)
    combined = [(r, True) for r in positives] + [(r, False) for r in sampled_neg]
    random.Random(seed + 1).shuffle(combined)

    q = to_internal(OUTSTANDING_QUESTION)
    kept_path = os.path.join(out_dir, "outstanding_rows.jsonl")
    items, strat = [], {}
    with open(kept_path, "w", encoding="utf-8") as out:
        for row_id, (r, is_pos) in enumerate(combined):
            state = m.build_stop_state(r.get("last_text_full") or "", message_chars)
            strat.setdefault(str(is_pos), []).append(row_id)
            items.append({"task": "outstanding", "row_id": row_id, "state": state, "question": q,
                          "target": noul_target(is_pos), "label": "true" if is_pos else "false",
                          "question_name": "will_run_outstanding"})
            out.write(json.dumps({"row_id": row_id, "label": r["label"], "session": r.get("session"),
                                  "project": r.get("project")}) + "\n")
    print(f"[outstanding] {len(positives)} positive, {len(sampled_neg)}/{len(negatives)} negatives sampled "
          f"(ratio {neg_ratio}); kept-row index -> {kept_path}", file=sys.stderr)
    return items, strat


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help="where train.jsonl and splits.json (and the outstanding survey's raw "
                         "session-text rows) are written; default $XDG_STATE_HOME/system-one/train "
                         "(or ~/.local/state/system-one/train) -- never the repo, these rows can "
                         "carry real session text")
    ap.add_argument("--agents-shared", default=default_agents_shared(),
                    help="agents-shared repo root (default: derived from this script's path)")
    ap.add_argument("--seed", type=int, default=0, help="split + downsample seed")
    ap.add_argument("--neg-ratio", type=float, default=4.0,
                    help="outstanding: negatives kept per positive (all positives are kept)")
    ap.add_argument("--skip-outstanding", action="store_true",
                    help="skip the command-moments-survey.py pass (for a quick rebuild of the other 4 tasks)")
    ap.add_argument("--python", default=sys.executable, help="interpreter to run command-moments-survey.py with")
    args = ap.parse_args()

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.makedirs(args.out_dir, exist_ok=True)
    m = load_measure_module(args.agents_shared)

    tasks = {}
    tasks["bash"] = build_bash_items(m, args.agents_shared)
    tasks["prompt"] = build_prompt_items(m, args.agents_shared)
    tasks["stop"] = build_stop_items(m, args.agents_shared)
    tasks["ask"] = build_ask_items(m, args.agents_shared)
    if not args.skip_outstanding:
        tasks["outstanding"] = build_outstanding_items(m, args.agents_shared, args.out_dir, args.seed,
                                                        args.neg_ratio, args.python)

    splits = {}
    row_split = {}  # (task, row_id) -> split
    for task, (items, strat) in tasks.items():
        sp = stratified_split(strat, args.seed)
        splits[task] = sp
        for split_name, ids in sp.items():
            for rid in ids:
                row_split[(task, rid)] = split_name

    data_path = os.path.join(args.out_dir, "train.jsonl")
    counts = {}
    with open(data_path, "w", encoding="utf-8") as out:
        for task, (items, _strat) in tasks.items():
            for it in items:
                split = row_split[(task, it["row_id"])]
                it["split"] = split
                out.write(json.dumps(it) + "\n")
                counts.setdefault(task, {}).setdefault(split, 0)
                counts[task][split] += 1

    splits_path = os.path.join(args.out_dir, "splits.json")
    with open(splits_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)

    print(f"wrote {data_path}")
    print(f"wrote {splits_path}")
    for task, by_split in counts.items():
        row_counts = {s: len(splits[task][s]) for s in ("train", "val", "test")}
        print(f"  {task:<12} items train/val/test = {by_split.get('train', 0)}/{by_split.get('val', 0)}/"
              f"{by_split.get('test', 0)}   rows train/val/test = {row_counts['train']}/{row_counts['val']}/"
              f"{row_counts['test']}")


if __name__ == "__main__":
    main()
