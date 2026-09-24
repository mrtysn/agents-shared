#!/usr/bin/env python3
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--device", choices=["cpu", "mps", "auto"], default="auto")
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--questions", default=DEFAULT_QUESTIONS_FILE)
    ap.add_argument("--threshold", type=float, default=None,
                    help="override every gate threshold with this one value")
    ap.add_argument("--sweep", action="store_true", help="joint grid over the gate thresholds")
    ap.add_argument("--first", type=int, default=0,
                    help="also report the gate on the first N rows (e.g. 30 = the original set)")
    ap.add_argument("-v", "--verbose", action="store_true", help="list the gate's misses and false asks")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    os.environ["HF_HUB_OFFLINE"] = "1"  # before import: no HTTP call can slip through
    import laya  # noqa: E402

    questions, gate, state_opts = load_questions(args.questions)
    keep = int(state_opts.get("heredoc_keep", 0))
    rows = load_cases(args.cases)
    gate_qs = [q for q in gate if q in questions]
    thr = {}
    ask_on = {}
    for q in gate_qs:
        t, a = gate_spec(gate, q, args.threshold)
        if args.threshold is not None:
            t = args.threshold
        if t is None:
            sys.exit(f"gate question {q!r} has no threshold and --threshold was not given")
        thr[q], ask_on[q] = t, a

    t0 = time.perf_counter()
    router = laya.Router(device=None if args.device == "auto" else args.device)
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
