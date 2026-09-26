#!/usr/bin/env python3
# DESC: Score the system-one hooks (bash/prompt/stop/ask) on their labelled case files with the exact state each hook builds
"""
system-one-measure: score the labelled Bash command set against the system-one
questions file and report recall / false-ask for the hook's gate.

Loads the Laya English checkpoint in-process, warms it once, then scores every row
of hooks/tests/system-one-bash-cases.tsv with the exact request the PreToolUse
Bash hook builds: the same questions file (hooks/system-one-bash-questions.json,
wording plus gate thresholds plus state normalisation) and the same heredoc
normaliser (hooks/system-one-bash-state.awk, run through awk so the two cannot
drift). Reports load time, p50/p95 latency, per-question precision/recall at the
file's thresholds, the gate's recall on should-ask rows and false-ask rate on
benign rows, and with --sweep a joint grid over every gate threshold reporting
the best point that keeps recall >= 0.95.

A row is "should ask" when any of its foreign_process / irreversible /
leaves_machine labels is 1 (the design doc's definition, section 3.1). The gate
fires when any question named in the file's "gate" reaches its threshold; a
question in the file but not in the gate is scored per-question only.

Runs fully offline: HF_HUB_OFFLINE=1 is set before laya is imported.

Usage (run with the system-one venv's interpreter, e.g.
$SYSTEM_ONE_VENV/bin/python):
    system-one-measure.py [--device {cpu,mps,auto}] [--cases FILE.tsv]
                          [--questions FILE.json] [--threshold T] [--sweep]
                          [--first N] [-v] [--json]
"""
import argparse
import itertools
import json
import os
import re
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_QUESTIONS_FILE = os.path.join(HERE, "..", "hooks", "system-one-bash-questions.json")
DEFAULT_CASES = os.path.join(HERE, "..", "hooks", "tests", "system-one-bash-cases.tsv")
STATE_AWK = os.path.join(HERE, "..", "hooks", "system-one-bash-state.awk")

CWD = "~/dev/project"  # placeholder cwd in the state string, not a real path
GOLD_COLUMNS = ("foreign_process", "irreversible", "leaves_machine")
EXTENDED_COLUMNS = (*GOLD_COLUMNS, "destructiveness", "target")
SWEEP_LEVELS = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # 0.30 .. 0.90


def load_questions(path: str) -> tuple[dict, dict, dict]:
    """Returns (questions, gate, state_opts). Accepts the flat shape too (no gate)."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if "questions" in doc:
        return doc["questions"], doc.get("gate", {}), doc.get("state", {})
    return doc, {}, {}


def unescape(s: str) -> str:
    # Inverse of the cases-file convention: \\, \n, \t escapes for embedded control
    # characters, so a heredoc command still fits on one TSV line.
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            n = s[i + 1]
            if n == "n":
                out.append("\n"); i += 2; continue
            if n == "t":
                out.append("\t"); i += 2; continue
            if n == "\\":
                out.append("\\"); i += 2; continue
        out.append(c); i += 1
    return "".join(out)


def load_cases(path: str) -> list[tuple[str, dict]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 6:
                raise ValueError(f"malformed cases row (expected 6 columns): {line!r}")
            cmd, fp, irr, lm, destr, target = fields
            rows.append((unescape(cmd), {
                "foreign_process": int(fp), "irreversible": int(irr), "leaves_machine": int(lm),
                "destructiveness": int(destr), "target": target,
            }))
    return rows


def normalise(cmd: str, keep: int) -> str:
    """Same transform the hook applies: awk -v KEEP=<n> -f system-one-bash-state.awk."""
    if not keep:
        return cmd
    res = subprocess.run(["awk", "-v", f"KEEP={keep}", "-f", STATE_AWK], input=cmd,
                         capture_output=True, text=True, check=True)
    return res.stdout.rstrip("\n")


def load_split_ids(splits_file: str, task: str, split_name: str) -> set:
    """row_ids for one task/split from splits.json (system-one-train-data.py's output:
    {task: {split: [row_id, ...]}}). row_id is the 0-based index of the case row within
    its TSV after blank/comment lines are stripped -- the same index load_cases(),
    ask_load_cases() and the prompt/stop loader below hand back in file order."""
    with open(splits_file, encoding="utf-8") as f:
        doc = json.load(f)
    if task not in doc:
        sys.exit(f"{splits_file}: no split data for task {task!r}")
    if split_name not in doc[task]:
        sys.exit(f"{splits_file}: task {task!r} has no split {split_name!r}")
    return set(doc[task][split_name])


def restrict_to_split(rows: list, args) -> list:
    """Filter a file-order row list down to the row_ids listed for args.split, when
    --splits/--split were given. row_id == position in `rows` (see load_split_ids)."""
    if not args.splits:
        return rows
    if not args.split:
        sys.exit("--splits given without --split")
    ids = load_split_ids(args.splits, args.hook, args.split)
    return [r for i, r in enumerate(rows) if i in ids]


def gate_spec(gate: dict, q: str, fallback: float | None):
    """(threshold, ask_on) for a gate question; ask_on is the choice-option list or None."""
    spec = gate.get(q)
    if spec is None:
        return None, None
    if isinstance(spec, dict):
        t = spec.get("threshold", fallback)
        return (float(t) if t is not None else None), spec.get("ask_on")
    return float(spec), None


def value(answer: dict, ask_on) -> float:
    """Normalise one answer to [0,1]: P(yes), score/(k-1), or P(ask_on classes)."""
    if answer.get("noul") is not None:
        return float(answer["noul"])
    if answer.get("score") is not None:
        k = max(len(answer.get("probabilities") or {}) - 1, 1)
        return float(answer["score"]) / k
    if answer.get("choice") is not None:
        probs = answer.get("probabilities") or {}
        return sum(float(probs.get(c, 0.0)) for c in (ask_on or []))
    return 0.0


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if (tp and p + r) else 0.0
    return p, r, f


def counts(rows, vals, thr: dict, idx=None):
    """Gate confusion over rows[idx]: gold = any GOLD_COLUMNS label; pred = any gate q >= thr."""
    idx = range(len(rows)) if idx is None else idx
    tp = fp = fn = tn = 0
    for i in idx:
        gold = any(rows[i][1][q] >= 1 for q in GOLD_COLUMNS)
        pred = any(vals[i].get(q, 0.0) >= t for q, t in thr.items())
        if gold and pred: tp += 1
        elif pred: fp += 1
        elif gold: fn += 1
        else: tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "recall": tp / (tp + fn) if tp + fn else float("nan"),
            "false_ask_rate": fp / (fp + tn) if fp + tn else float("nan")}


def sweep(rows, vals, gate_qs):
    """Joint grid over gate thresholds. Returns the Pareto frontier (for each recall
    level reached, the lowest false-ask and the thresholds that give it) and the
    chosen point: lowest false-ask among points with recall >= 0.95 if any reach it,
    else the point with the largest recall minus false-ask."""
    import numpy as np
    gold = np.array([any(r[1][q] >= 1 for q in GOLD_COLUMNS) for r in rows])
    v = np.array([[vals[i].get(q, 0.0) for q in gate_qs] for i in range(len(rows))])
    n_pos, n_neg = gold.sum(), (~gold).sum()
    frontier = {}
    for combo in itertools.product(SWEEP_LEVELS, repeat=len(gate_qs)):
        pred = (v >= np.array(combo)).any(axis=1)
        rec = round(float((pred & gold).sum() / n_pos), 4) if n_pos else 0.0
        far = round(float((pred & ~gold).sum() / n_neg), 4) if n_neg else 0.0
        if rec not in frontier or far < frontier[rec]["false_ask_rate"]:
            frontier[rec] = {"recall": rec, "false_ask_rate": far, "thresholds": dict(zip(gate_qs, combo))}
    # keep only points no other point dominates
    pts = sorted(frontier.values(), key=lambda p: -p["recall"])
    pareto, best_far = [], 2.0
    for p in pts:
        if p["false_ask_rate"] < best_far:
            pareto.append(p); best_far = p["false_ask_rate"]
    ok = [p for p in pareto if p["recall"] >= 0.95]
    chosen = min(ok, key=lambda p: p["false_ask_rate"]) if ok else \
        max(pareto, key=lambda p: p["recall"] - p["false_ask_rate"])
    return {"pareto": sorted(pareto, key=lambda p: p["recall"]), "chosen": chosen}


STRUCT_TABLE = re.compile(r"^\s*\|.*\|\s*$")
STRUCT_HEADER = re.compile(r"^#{1,6}\s")
STRUCT_BULLET = re.compile(r"^\s*([-*]|[0-9]+\.)\s")


def stop_structure(text: str):
    """The length_chars/tables/headers/bullets line, computed exactly as
    hooks/system-one-stop.sh computes it (same three regexes, over every
    line of the full message)."""
    lines = text.splitlines()
    return (len(text),
            sum(1 for ln in lines if STRUCT_TABLE.match(ln)),
            sum(1 for ln in lines if STRUCT_HEADER.match(ln)),
            sum(1 for ln in lines if STRUCT_BULLET.match(ln)))


def unescape_nl(text: str) -> str:
    """Cases files keep one row per line; a message's newlines are stored as
    a literal backslash-n (scripts/usage-survey.py --dump-stops writes them
    that way, and hooks/tests/run-system-one-stop.sh undoes it the same way)."""
    return text.replace("\\n", "\n")


def build_prompt_state(text: str, prev: str, prompt_chars: int, previous_chars: int) -> str:
    """State for hooks/system-one-prompt.sh: the prompt cut to prompt_chars, plus an
    optional previous: excerpt of the last assistant message's final previous_chars
    characters. Shared with system-one-train-data.py so the fine-tune sees exactly
    the state the hook builds."""
    state = f"prompt:\n{text[:prompt_chars]}"
    if previous_chars and prev:
        state += f"\nprevious:\n{prev[-previous_chars:]}"
    return state


def build_stop_state(text: str, message_chars: int) -> str:
    """State for hooks/system-one-stop.sh: the assistant message cut to message_chars,
    plus the length_chars/tables/headers/bullets summary line. Shared with
    system-one-train-data.py."""
    length, tables, headers, bullets = stop_structure(text)
    return (f"assistant message:\n{text[:message_chars]}\n"
            f"length_chars: {length}  tables: {tables}  headers: {headers}  bullets: {bullets}")


def build_correct_state(prev_prompt: str, reply: str, prompt_chars: int = 400, message_chars: int = 1500) -> str:
    """State for will_correct: the user's previous prompt (the one that led to
    `reply`) plus the reply's own build_stop_state block -- "correction after a
    correction" is the strongest observed pattern, so the previous prompt goes in
    the state alongside the reply it produced. Byte-reproducible: the Stop hook
    builds the same string at runtime from the transcript's previous human prompt
    and its own final message."""
    return (f"previous prompt:\n{(prev_prompt or '')[:prompt_chars]}\n\n"
            f"reply:\n{build_stop_state(reply, message_chars)}")


ASK_QUESTION_KEYS = ("answered_in_context", "routine_default", "naming_or_irreversible", "options_complete")
ASK_CASE_COLUMNS = ("answered_in_context", "routine_default", "naming_or_irreversible", "options_complete",
                    "call", "index", "count", "project", "question_json", "answer", "recent")


def ask_question_lines(q: dict, desc_chars: int) -> list:
    """One question's lines, exactly as hooks/system-one-ask.sh's jq builds
    them: "header: question", the multiSelect flag, and the options with
    descriptions cut to desc_chars."""
    opts = q.get("options") or []
    return [
        f"{q.get('header') or ''}: {q.get('question') or ''}",
        f"multiSelect: {'true' if q.get('multiSelect') else 'false'}",
        "options: " + "; ".join(f"{o.get('label') or ''} ({(o.get('description') or '')[:desc_chars]})" for o in opts),
    ]


def ask_recent_block(recent: str, prompts: int, chars: int) -> str:
    """The recent: block the hook builds from the transcript tail: the last
    `prompts` typed user prompts, each cut to its last `chars` characters,
    then the last assistant text's last `chars` characters. The cases file
    stores up to 5 prompts at 600 characters; this cuts it down the same way
    the hook's jq does (.[-n:] on each message)."""
    if prompts <= 0 or chars <= 0:
        return ""
    lines = recent.split("\\n")
    users = [ln[len("user: "):] for ln in lines if ln.startswith("user: ")][-prompts:]
    asst = [ln[len("assistant: "):] for ln in lines if ln.startswith("assistant: ")]
    out = [f"user: {u[-chars:]}" for u in users]
    if asst:
        out.append(f"assistant: {asst[-1][-chars:]}")
    return "\n".join(out)


def ask_state(questions: list, recent_block: str, desc_chars: int) -> str:
    """Mirrors hooks/system-one-ask.sh: one question ("question:" + its
    lines) or, for a whole-ask state, "questions:" + every question's lines
    as list items, then the recent: block."""
    if len(questions) == 1:
        lines = ["question:"] + ask_question_lines(questions[0], desc_chars)
    else:
        lines = ["questions:"]
        for q in questions:
            ql = ask_question_lines(q, desc_chars)
            lines.append("- " + ql[0])
            lines.extend("  " + x for x in ql[1:])
    state = "\n".join(lines)
    if recent_block:
        state += "\nrecent:\n" + recent_block
    return state


def ask_load_cases(cases_file: str) -> list:
    rows = []
    with open(cases_file, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) < len(ASK_CASE_COLUMNS):
                continue
            r = dict(zip(ASK_CASE_COLUMNS, fields))
            rows.append({
                "gold": {k: int(r[k]) for k in ASK_QUESTION_KEYS},
                "call": r["call"], "index": int(r["index"]), "count": int(r["count"]),
                "question": json.loads(r["question_json"].replace("\\n", "\n")),
                "answer": r["answer"], "recent": r["recent"],
            })
    return rows


def best_threshold(pairs: list) -> dict:
    """The threshold with the best F1 over the (gold, score) pairs, swept
    over every distinct score; reports P/R/F1 and the count that would fire."""
    best = {"threshold": None, "precision": 0.0, "recall": 0.0, "f1": 0.0, "fires": 0}
    for thr in sorted({round(s, 3) for _, s in pairs}):
        tp = sum(1 for g, s in pairs if g and s >= thr)
        fp = sum(1 for g, s in pairs if not g and s >= thr)
        fn = sum(1 for g, s in pairs if g and s < thr)
        p, r, f1 = prf(tp, fp, fn)
        if f1 > best["f1"]:
            best = {"threshold": thr, "precision": p, "recall": r, "f1": f1, "fires": tp + fp}
    return best


def measure_ask(args) -> None:
    """--hook ask: score hooks/tests/system-one-ask-cases.tsv (one row per
    question; see its header) against hooks/system-one-ask-questions.json's
    noul questions, building exactly the state hooks/system-one-ask.sh
    builds: one call per question by default, or one call per
    AskUserQuestion call with --whole-ask (gold aggregated over the call's
    questions: any answered_in_context / routine_default /
    naming_or_irreversible, all options_complete). Reports per-question
    precision/recall at the file's gate threshold (0.50 for a question the
    gate does not name), the best-F1 threshold, and a 2x2 confusion matrix
    for options_complete."""
    import laya  # noqa: E402

    here = os.path.dirname(os.path.abspath(__file__))
    default_questions = os.path.join(here, "..", "hooks", "system-one-ask-questions.json")
    default_cases = os.path.join(here, "..", "hooks", "tests", "system-one-ask-cases.tsv")
    questions_file = args.questions if args.questions != DEFAULT_QUESTIONS_FILE else default_questions
    cases_file = args.cases if args.cases != DEFAULT_CASES else default_cases

    with open(questions_file, encoding="utf-8") as f:
        doc = json.load(f)
    questions = doc["questions"]
    keys = [k for k in ASK_QUESTION_KEYS if k in questions]
    gate = doc.get("gate", {})
    state_opts = doc.get("state", {})
    recent_chars = 0 if args.no_recent else (
        args.recent_chars if args.recent_chars is not None else int(state_opts.get("recent_chars", 150)))
    recent_prompts = 0 if args.no_recent else (
        args.recent_prompts if args.recent_prompts is not None else int(state_opts.get("recent_prompts", 3)))
    desc_chars = int(state_opts.get("description_chars", 50))

    rows = ask_load_cases(cases_file)
    rows = restrict_to_split(rows, args)
    if not rows:
        sys.exit(f"no rows in {cases_file}")

    # Units to score: one per question, or one per call with --whole-ask.
    units = []
    if args.whole_ask:
        by_call = {}
        for r in rows:
            by_call.setdefault(r["call"], []).append(r)
        for call, group in by_call.items():
            group.sort(key=lambda r: r["index"])
            gold = {
                "answered_in_context": max(r["gold"]["answered_in_context"] for r in group),
                "routine_default": max(r["gold"]["routine_default"] for r in group),
                "naming_or_irreversible": max(r["gold"]["naming_or_irreversible"] for r in group),
                "options_complete": min(r["gold"]["options_complete"] for r in group),
            }
            units.append({"id": call, "gold": gold, "questions": [r["question"] for r in group],
                          "recent": group[0]["recent"], "answer": " | ".join(r["answer"] for r in group)})
    else:
        for r in rows:
            units.append({"id": f"{r['call']}#{r['index']}", "gold": r["gold"], "questions": [r["question"]],
                          "recent": r["recent"], "answer": r["answer"]})
    for u in units:
        u["state"] = ask_state(u["questions"], ask_recent_block(u["recent"], recent_prompts, recent_chars), desc_chars)

    t0 = time.perf_counter()
    router = laya.Router(device=None if args.device == "auto" else args.device,
                         models={"english": args.model_dir} if args.model_dir else None)
    router.predict(units[0]["state"], questions, model="english")
    load_s = time.perf_counter() - t0

    preds, lat = [], []
    dump = open(args.dump_preds, "w", encoding="utf-8") if args.dump_preds else None
    for u in units:
        t = time.perf_counter()
        res = router.predict(u["state"], questions, model="english")
        lat.append((time.perf_counter() - t) * 1000)
        p = {k: res["answers"].get(k, {}).get("noul", 0.0) for k in keys}
        preds.append(p)
        if dump:
            dump.write(f"{u['id']}\t" + "\t".join(f"{k}={u['gold'][k]}/{p[k]:.2f}" for k in keys)
                       + f"\t{u['answer'][:60]!r}\n")
    if dump:
        dump.close()

    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted) if lat_sorted else 0.0
    p95 = lat_sorted[int(round(0.95 * (len(lat_sorted) - 1)))] if lat_sorted else 0.0

    per_question = {}
    for q in keys:
        thr = float(args.thresholds.get(q, gate.get(q, 0.50)))
        tp = fp = fn = tn = 0
        for u, p in zip(units, preds):
            gold, pred = u["gold"][q] >= 1, p[q] >= thr
            if gold and pred: tp += 1
            elif pred: fp += 1
            elif gold: fn += 1
            else: tn += 1
        precision, recall, f1 = prf(tp, fp, fn)
        per_question[q] = {"threshold": thr, "precision": precision, "recall": recall, "f1": f1,
                           "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n_pos": tp + fn,
                           "best": best_threshold([(u["gold"][q] >= 1, p[q]) for u, p in zip(units, preds)])}

    confusion = None
    if "options_complete" in keys:
        oc_thr = per_question["options_complete"]["threshold"]
        confusion = {"gold=1(complete)": {"pred=1": 0, "pred=0": 0}, "gold=0(off-option)": {"pred=1": 0, "pred=0": 0}}
        for u, p in zip(units, preds):
            g = "gold=1(complete)" if u["gold"]["options_complete"] >= 1 else "gold=0(off-option)"
            pk = "pred=1" if p["options_complete"] >= oc_thr else "pred=0"
            confusion[g][pk] += 1

    summary = {"hook": "ask", "device": args.device, "load_s": round(load_s, 2), "p50_ms": round(p50, 1),
               "p95_ms": round(p95, 1), "n": len(units), "unit": "call" if args.whole_ask else "question",
               "recent_prompts": recent_prompts, "recent_chars": recent_chars,
               "questions_file": questions_file, "cases_file": cases_file,
               "per_question": per_question, "options_complete_confusion": confusion}
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"hook=ask device={args.device} load_s={load_s:.2f} p50_ms={p50:.1f} p95_ms={p95:.1f} n={len(units)} "
          f"unit={summary['unit']} recent_prompts={recent_prompts} recent_chars={recent_chars} "
          f"questions={os.path.relpath(questions_file)} cases={os.path.relpath(cases_file)}")
    print(f"{'question':<24}{'pos':>5}{'thr':>6}{'P':>7}{'R':>7}{'F1':>7}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>5}"
          f"   best-F1 thr / P / R / F1 / fires")
    for q, m in per_question.items():
        b = m["best"]
        print(f"{q:<24}{m['n_pos']:>5}{m['threshold']:>6.2f}{m['precision']:>7.2f}{m['recall']:>7.2f}{m['f1']:>7.2f}"
              f"{m['tp']:>5}{m['fp']:>5}{m['fn']:>5}{m['tn']:>5}"
              f"   {b['threshold'] if b['threshold'] is not None else '-':>5} / {b['precision']:.2f} / {b['recall']:.2f} / {b['f1']:.2f} / {b['fires']}")
    if confusion:
        print(f"options_complete confusion (threshold {per_question['options_complete']['threshold']:.2f}):")
        print(f"  {'':<20}{'pred=1':>8}{'pred=0':>8}")
        for g, row in confusion.items():
            print(f"  {g:<20}{row['pred=1']:>8}{row['pred=0']:>8}")


def measure_classifier(args) -> None:
    """--hook prompt / --hook stop: score a classification cases file (not the
    6-column gate cases file) against the hook's questions, and report
    per-class precision/recall and a confusion matrix. The state is built the
    way the hook builds it, from the same questions file, so a number here is
    a number for the hook. Imports laya itself (main() already set
    HF_HUB_OFFLINE before calling in)."""
    import laya  # noqa: E402

    here = os.path.dirname(os.path.abspath(__file__))
    default_questions = {
        "prompt": os.path.join(here, "..", "hooks", "system-one-prompt-questions.json"),
        "stop": os.path.join(here, "..", "hooks", "system-one-stop-questions.json"),
    }[args.hook]
    default_cases = {
        "prompt": os.path.join(here, "..", "hooks", "tests", "system-one-prompt-cases.tsv"),
        "stop": os.path.join(here, "..", "hooks", "tests", "system-one-stop-cases.tsv"),
    }[args.hook]
    questions_file = args.questions if args.questions != DEFAULT_QUESTIONS_FILE else default_questions
    cases_file = args.cases if args.cases != DEFAULT_CASES else default_cases

    with open(questions_file, encoding="utf-8") as f:
        doc = json.load(f)
    questions = doc["questions"]
    gate = dict(doc.get("gate", {}))
    if "needless_table" in args.thresholds:
        gate["needless_table_min"] = float(args.thresholds["needless_table"])
    if "overlong" in args.thresholds:
        gate["overlong_min"] = float(args.thresholds["overlong"])
    state_opts = doc.get("state", {})
    pregate = doc.get("pregate", {})
    prompt_chars = args.prompt_chars if args.prompt_chars is not None else int(state_opts.get("prompt_chars", 600))
    previous_chars = 0 if args.no_previous else (
        args.previous_chars if args.previous_chars is not None else int(state_opts.get("previous_chars", 300)))
    message_chars = int(state_opts.get("message_chars", 1500))

    rows = []
    with open(cases_file, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if args.hook == "prompt":
                if len(fields) < 3:
                    continue
                rows.append({"gold": fields[0], "wants_action": fields[1], "text": fields[2],
                             "prev": unescape_nl(fields[3]) if len(fields) > 3 else ""})
            else:
                if len(fields) < 2:
                    continue
                rows.append({"gold": fields[0], "text": unescape_nl("\t".join(fields[1:]))})
    rows = restrict_to_split(rows, args)

    def prompt_state(r):
        return build_prompt_state(r["text"], r["prev"], prompt_chars, previous_chars)

    def stop_state(r):
        return build_stop_state(r["text"], message_chars)

    t0 = time.perf_counter()
    router = laya.Router(device=None if args.device == "auto" else args.device,
                         models={"english": args.model_dir} if args.model_dir else None)
    router.predict(prompt_state({"text": "warm up", "prev": ""}) if args.hook == "prompt"
                   else stop_state({"text": "warm up"}), questions, model="english")
    load_s = time.perf_counter() - t0

    preds, lat, skipped = [], [], 0
    dump = open(args.dump_preds, "w", encoding="utf-8") if args.dump_preds else None
    for r in rows:
        if args.hook == "stop" and pregate:
            # Deterministic pre-gate, the same rule the hook applies before
            # calling the model: a short message with no table is never padded.
            length, tables, _, _ = stop_structure(r["text"])
            if length < int(pregate.get("max_chars", 0)) and tables == 0:
                preds.append("fitting"); skipped += 1
                if dump:
                    dump.write(f"{r['gold']}\tfitting\tpregate\t{r['text'][:60]!r}\n")
                continue
        state = prompt_state(r) if args.hook == "prompt" else stop_state(r)
        t = time.perf_counter()
        res = router.predict(state, questions, model="english")
        lat.append((time.perf_counter() - t) * 1000)
        ans = res["answers"]
        if args.hook == "prompt":
            # Two-stage when the file carries is_correction + gate.correction_min
            # (hooks/system-one-prompt.sh applies the same rule): a correction
            # is decided by its own noul first, the choice settles the rest.
            corr = ans.get("is_correction", {}).get("noul")
            if corr is not None and "correction_min" in gate and corr >= gate["correction_min"]:
                pred = "correction"
            else:
                pred = ans.get("kind", {}).get("choice", "other")
            detail = json.dumps({k: (v.get("probabilities") or v.get("noul")) for k, v in ans.items()})
        else:
            # Same firing rule as hooks/system-one-stop.sh's act mode: block
            # (predict "padded") when needless_table reaches gate.needless_table_min
            # or overlong reaches gate.overlong_min; a threshold the file
            # does not set never fires.
            overlong = ans.get("overlong", {}).get("noul", 0.0)
            table = ans.get("needless_table", {}).get("noul", 0.0)
            fires = (table >= gate.get("needless_table_min", 2.0)) or \
                    (overlong >= gate.get("overlong_min", 2.0))
            pred = "padded" if fires else "fitting"
            detail = json.dumps({k: round(v.get("noul", v.get("score", 0.0)), 3) for k, v in ans.items()})
        preds.append(pred)
        if dump:
            dump.write(f"{r['gold']}\t{pred}\t{detail}\t{r['text'][:60]!r}\n")
    if dump:
        dump.close()

    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted) if lat_sorted else 0.0
    p95 = lat_sorted[int(round(0.95 * (len(lat_sorted) - 1)))] if lat_sorted else 0.0

    classes = sorted({r["gold"] for r in rows} | set(preds))
    confusion = {g: {p: 0 for p in classes} for g in classes}
    correct = 0
    for r, pred in zip(rows, preds):
        confusion[r["gold"]][pred] += 1
        if pred == r["gold"]:
            correct += 1
    accuracy = correct / len(rows) if rows else 0.0
    per_class = {}
    for c in classes:
        tp = confusion[c][c]
        fn = sum(confusion[c].values()) - tp
        fp = sum(confusion[g][c] for g in classes if g != c)
        per_class[c] = {
            "n": sum(confusion[c].values()),
            "recall": tp / (tp + fn) if (tp + fn) else float("nan"),
            "precision": tp / (tp + fp) if (tp + fp) else float("nan"),
        }

    summary = {
        "hook": args.hook, "device": args.device, "load_s": round(load_s, 2),
        "p50_ms": round(p50, 1), "p95_ms": round(p95, 1), "n": len(rows), "pregate_skipped": skipped,
        "prompt_chars": prompt_chars, "previous_chars": previous_chars,
        "questions_file": questions_file, "cases_file": cases_file,
        "accuracy": accuracy, "per_class": per_class, "confusion": confusion,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
        return
    print(f"hook={args.hook} device={args.device} load_s={load_s:.2f} p50_ms={p50:.1f} p95_ms={p95:.1f} "
          f"n={len(rows)} pregate_skipped={skipped} prompt_chars={prompt_chars} previous_chars={previous_chars} "
          f"questions={os.path.relpath(questions_file)} cases={os.path.relpath(cases_file)}")
    print(f"overall accuracy: {accuracy:.3f}")
    print(f"{'class':<14}{'n':>5}{'precision':>11}{'recall':>9}")
    for c in classes:
        m = per_class[c]
        print(f"{c:<14}{m['n']:>5}{m['precision']:>11.2f}{m['recall']:>9.2f}")
    print("confusion matrix (rows=gold, cols=predicted):")
    header = " " * 14 + "".join(f"{c:>10}" for c in classes)
    print(header)
    for g in classes:
        print(f"{g:<14}" + "".join(f"{confusion[g][p]:>10}" for p in classes))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--device", choices=["cpu", "mps", "auto"], default="auto")
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--questions", default=DEFAULT_QUESTIONS_FILE)
    ap.add_argument("--model-dir", metavar="DIR",
                    help="score a local fine-tuned checkpoint directory instead of the base "
                         "'english' model (Router(models={'english': DIR}); no other code path changes)")
    ap.add_argument("--splits", metavar="FILE",
                    help="splits.json written by system-one-train-data.py (task -> split -> "
                         "[row_id, ...]); restricts scored rows to --split for this --hook's task")
    ap.add_argument("--split", choices=["train", "val", "test"],
                    help="which split to restrict to when --splits is given")
    ap.add_argument("--threshold", type=float, default=None,
                    help="override every gate threshold with this one value")
    ap.add_argument("--thresholds", metavar="JSON", default=None,
                    help="per-question threshold overrides, e.g. '{\"irreversible\": 0.6}' (bash gate, ask "
                         "gate) or '{\"needless_table\": 0.4}' (stop): apply thresholds swept on --split val "
                         "to --split test unchanged")
    ap.add_argument("--sweep", action="store_true", help="joint grid over the gate thresholds")
    ap.add_argument("--first", type=int, default=0,
                    help="also report the gate on the first N rows (e.g. 30 = the original set)")
    ap.add_argument("-v", "--verbose", action="store_true", help="list the gate's misses and false asks")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--hook", choices=["bash", "prompt", "stop", "ask"], default="bash",
                    help="which hook's cases/questions shape to score. 'bash' is the original path "
                         "(gate recall/false-ask over the 6-column cases file); 'prompt' and 'stop' "
                         "score a classification cases file (label<TAB>...<TAB>text) against the "
                         "'kind' choice question (prompt) or 'verbosity'/noul questions (stop) and "
                         "report per-class accuracy plus a confusion matrix; 'ask' scores the "
                         "AskUserQuestion pre-check's four noul questions per-question (precision/"
                         "recall plus a confusion matrix for options_complete).")
    ap.add_argument("--no-previous", action="store_true",
                    help="prompt: build the state without the previous: excerpt")
    ap.add_argument("--previous-chars", type=int, default=None,
                    help="prompt: override state.previous_chars from the questions file")
    ap.add_argument("--prompt-chars", type=int, default=None,
                    help="prompt: override state.prompt_chars from the questions file")
    ap.add_argument("--dump-preds", metavar="FILE",
                    help="prompt/stop/ask: write gold<TAB>pred<TAB>answers<TAB>excerpt per row")
    ap.add_argument("--whole-ask", action="store_true",
                    help="ask: one state per AskUserQuestion call (every question in it) instead of one per question")
    ap.add_argument("--recent-prompts", type=int, default=None,
                    help="ask: override state.recent_prompts from the questions file")
    ap.add_argument("--recent-chars", type=int, default=None,
                    help="ask: override state.recent_chars from the questions file")
    ap.add_argument("--no-recent", action="store_true", help="ask: build the state without the recent: block")
    args = ap.parse_args()
    args.thresholds = json.loads(args.thresholds) if args.thresholds else {}

    os.environ["HF_HUB_OFFLINE"] = "1"  # before import: no HTTP call can slip through
    import laya  # noqa: E402

    if args.hook in ("prompt", "stop"):
        measure_classifier(args)
        return
    if args.hook == "ask":
        measure_ask(args)
        return

    questions, gate, state_opts = load_questions(args.questions)
    keep = int(state_opts.get("heredoc_keep", 0))
    rows = load_cases(args.cases)
    rows = restrict_to_split(rows, args)
    gate_qs = [q for q in gate if q in questions]
    thr = {}
    ask_on = {}
    for q in gate_qs:
        t, a = gate_spec(gate, q, args.threshold)
        if args.threshold is not None:
            t = args.threshold
        if q in args.thresholds:
            t = float(args.thresholds[q])
        if t is None:
            sys.exit(f"gate question {q!r} has no threshold and --threshold was not given")
        thr[q], ask_on[q] = t, a

    t0 = time.perf_counter()
    router = laya.Router(device=None if args.device == "auto" else args.device,
                         models={"english": args.model_dir} if args.model_dir else None)
    router.predict(f"cwd: {CWD}\ncommand:\nls", questions)
    load_s = time.perf_counter() - t0

    vals, choices, lat = [], [], []
    for cmd, _label in rows:
        state = f"cwd: {CWD}\ncommand:\n{normalise(cmd, keep)}"
        t = time.perf_counter()
        res = router.predict(state, questions)
        lat.append((time.perf_counter() - t) * 1000)
        ans = res["answers"]
        vals.append({q: value(a, ask_on.get(q)) for q, a in ans.items()})
        choices.append({q: a.get("choice") for q, a in ans.items() if a.get("choice") is not None})
    lat_sorted = sorted(lat)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[int(round(0.95 * (len(lat_sorted) - 1)))]

    # per-question P/R for every question that has a gold column, at its gate threshold
    per_question = {}
    for q in questions:
        if q not in EXTENDED_COLUMNS or q == "target":
            continue
        t = thr.get(q, args.threshold if args.threshold is not None else 0.70)
        tp = fp = fn = tn = 0
        for i, (_c, label) in enumerate(rows):
            g, p = label[q] >= 1, vals[i].get(q, 0.0) >= t
            if g and p: tp += 1
            elif p: fp += 1
            elif g: fn += 1
            else: tn += 1
        P, R, F = prf(tp, fp, fn)
        per_question[q] = {"threshold": t, "precision": P, "recall": R, "f1": F, "tp": tp, "fp": fp, "fn": fn, "tn": tn}
    target_acc = None
    if "target" in questions:
        target_acc = sum(1 for i, r in enumerate(rows) if choices[i].get("target") == r[1]["target"]) / len(rows)

    overall = counts(rows, vals, thr)
    first = counts(rows, vals, thr, range(min(args.first, len(rows)))) if args.first else None
    swept = sweep(rows, vals, gate_qs) if args.sweep and gate_qs else None

    summary = {"device": args.device, "load_s": round(load_s, 2), "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
               "n": len(rows), "questions_file": args.questions, "heredoc_keep": keep, "gate": thr,
               "per_question": per_question, "target_accuracy": target_acc, "overall": overall,
               "first": first, "sweep": swept}
    if args.json:
        summary["rows"] = [{"cmd": rows[i][0], "label": rows[i][1], "values": vals[i], "ms": round(lat[i], 1)}
                           for i in range(len(rows))]
        print(json.dumps(summary, indent=2))
        return

    print(f"device={args.device} load_s={load_s:.2f} p50_ms={p50:.1f} p95_ms={p95:.1f} n={len(rows)} "
          f"heredoc_keep={keep} questions={os.path.relpath(args.questions)}")
    print(f"gate: {json.dumps(thr)}")
    print(f"{'question':<18}{'thr':>6}{'P':>7}{'R':>7}{'F1':>7}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>5}")
    for q, m in per_question.items():
        print(f"{q:<18}{m['threshold']:>6.2f}{m['precision']:>7.2f}{m['recall']:>7.2f}{m['f1']:>7.2f}"
              f"{m['tp']:>5}{m['fp']:>5}{m['fn']:>5}{m['tn']:>5}")
    if target_acc is not None:
        print(f"target accuracy: {target_acc:.2f}")

    def line(tag, c):
        print(f"{tag}: recall(should-ask)={c['recall']:.2f} false_ask_rate(benign)={c['false_ask_rate']:.2f} "
              f"tp={c['tp']} fp={c['fp']} fn={c['fn']} tn={c['tn']}")
    line("overall", overall)
    if first:
        line(f"first {args.first}", first)
    if args.verbose:
        for i, (cmd, label) in enumerate(rows):
            gold = any(label[q] >= 1 for q in GOLD_COLUMNS)
            fired = [f"{q}={vals[i].get(q, 0.0):.2f}" for q, t in thr.items() if vals[i].get(q, 0.0) >= t]
            if gold and not fired:
                print(f"  MISS  {cmd[:70]!r}  " + " ".join(f"{q}={vals[i].get(q, 0.0):.2f}" for q in thr))
            elif fired and not gold:
                print(f"  FALSE {cmd[:70]!r}  " + " ".join(fired))
    if swept:
        print(f"sweep ({len(SWEEP_LEVELS)}^{len(gate_qs)} points) Pareto frontier, recall -> lowest false-ask:")
        for p in swept["pareto"]:
            print(f"  recall={p['recall']:.2f} false_ask={p['false_ask_rate']:.2f} thresholds={json.dumps(p['thresholds'])}")
        c = swept["chosen"]
        print(f"chosen (recall >= 0.95 at lowest false-ask, else max recall minus false-ask): "
              f"recall={c['recall']:.2f} false_ask={c['false_ask_rate']:.2f} thresholds={json.dumps(c['thresholds'])}")


if __name__ == "__main__":
    main()
