#!/usr/bin/env python3
# DESC: Evaluate a noul task mined by system-one-mine-tasks.py (will_correct, delegate) against a precision-at-recall bar, val-swept threshold applied to test, base vs fine-tuned
"""
system-one-eval-tasks: score one noul-type task JSONL from
scripts/system-one-mine-tasks.py (will_correct.jsonl, delegate.jsonl, or any
file sharing that row schema: {"task","split","row_id","state","label",...})
against a checkpoint (or the base Laya model), for a "precision >= P at
recall >= R" bar.

For each row's own state, calls laya.Agent(model_dir).predict_batch with the
task's own external question definition (kept here verbatim, matching
scripts/system-one-mine-tasks.py's WILL_CORRECT_QUESTION / DELEGATE_QUESTION)
and reads P(true) from the noul answer. Threshold is swept over the val
split in steps of 0.01; among thresholds meeting --min-precision at
--min-recall, the one with the highest recall is chosen (ties: highest
precision); if none qualify, the closest miss is reported and the run is
marked FAIL. That threshold (plus 0.5/0.6/0.7 fixed points) is then scored
once on the test split. Balanced accuracy is macro recall over the two
classes at the chosen threshold.

Runs fully offline (HF_HUB_OFFLINE=1 set before importing laya); the base
model is loaded from the local hub cache like scripts/system-one-train.py.

Usage (system-one venv's python):
    system-one-eval-tasks.py --task will_correct --data will_correct.jsonl \\
        --splits splits-v3.json --model-dir DIR --min-precision 0.60 --min-recall 0.40
    system-one-eval-tasks.py --task delegate --data delegate.jsonl \\
        --splits splits-v3.json --model-dir DIR --min-precision 0.70 --min-recall 0.0 \\
        --positive-label spawn
"""
import argparse
import json
import os
import sys

TASK_QUESTIONS = {
    "will_correct": {
        "question": {
            "type": "noul",
            "instructions": "Will the user's next typed message be a correction -- saying the "
                            "previous action or answer was wrong or unwanted?",
        },
        "positive_label": "true",
    },
    "delegate": {
        "question": {
            "type": "noul",
            "instructions": "Should this prompt be handed to a subagent rather than done inline?",
        },
        "positive_label": "spawn",
    },
}


def read_rows(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else float("nan")
    r = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * p * r / (p + r) if (p == p and r == r and (p + r) > 0) else 0.0
    return p, r, f1


def confusion_at(golds, probs, thr):
    tp = fp = fn = tn = 0
    for g, p in zip(golds, probs):
        pred = p >= thr
        if g and pred:
            tp += 1
        elif pred:
            fp += 1
        elif g:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def bal_acc(tp, fp, fn, tn):
    rec_pos = tp / (tp + fn) if (tp + fn) else float("nan")
    rec_neg = tn / (tn + fp) if (tn + fp) else float("nan")
    vals = [v for v in (rec_pos, rec_neg) if v == v]
    return sum(vals) / len(vals) if vals else float("nan")


def sweep_threshold(golds, probs, min_precision, min_recall):
    best = None
    closest = None
    closest_gap = None
    for i in range(0, 101):
        thr = i / 100.0
        tp, fp, fn, tn = confusion_at(golds, probs, thr)
        p, r, f1 = prf(tp, fp, fn)
        ok = (p == p) and p >= min_precision and r >= min_recall
        gap = max(0.0, min_precision - (p if p == p else 0.0)) + max(0.0, min_recall - r)
        if closest_gap is None or gap < closest_gap:
            closest_gap = gap
            closest = {"threshold": thr, "precision": p, "recall": r, "f1": f1}
        if ok and (best is None or r > best["recall"] or (r == best["recall"] and p > best["precision"])):
            best = {"threshold": thr, "precision": p, "recall": r, "f1": f1}
    return best, closest


def score_rows(agent, question, rows, batch_size):
    states = [r["state"] for r in rows]
    results = agent.predict_batch(states, {"q": question}, batch_size=batch_size)
    return [float(res["answers"]["q"]["noul"]) for res in results]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--task", required=True, choices=sorted(TASK_QUESTIONS))
    ap.add_argument("--data", required=True, help="task JSONL (e.g. will_correct.jsonl)")
    ap.add_argument("--splits", required=True, help="splits-v3.json (or any file with task -> split -> [row_id])")
    ap.add_argument("--model-dir", default=None, help="checkpoint dir; omit to score the base model")
    ap.add_argument("--base", default="convaiinnovations/laya", help="base checkpoint id, used when --model-dir is omitted")
    ap.add_argument("--positive-label", default=None, help="override the task's default positive label")
    ap.add_argument("--min-precision", type=float, required=True)
    ap.add_argument("--min-recall", type=float, required=True)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    os.environ["HF_HUB_OFFLINE"] = "1"
    import laya  # noqa: E402

    spec = TASK_QUESTIONS[args.task]
    question = spec["question"]
    pos_label = args.positive_label or spec["positive_label"]

    rows = read_rows(args.data)
    with open(args.splits, encoding="utf-8") as f:
        splits = json.load(f)
    split_ids = splits.get(args.task, {})
    val_ids = set(split_ids.get("val", []))
    test_ids = set(split_ids.get("test", []))
    val_rows = [r for r in rows if r["row_id"] in val_ids]
    test_rows = [r for r in rows if r["row_id"] in test_ids]
    if not val_rows or not test_rows:
        sys.exit(f"no val/test rows found for task={args.task} in {args.data} against {args.splits}")

    model_ref = args.model_dir or args.base
    agent = laya.Agent(model_ref, device=args.device)

    val_probs = score_rows(agent, question, val_rows, args.batch_size)
    test_probs = score_rows(agent, question, test_rows, args.batch_size)
    val_golds = [r["label"] == pos_label for r in val_rows]
    test_golds = [r["label"] == pos_label for r in test_rows]

    chosen, closest = sweep_threshold(val_golds, val_probs, args.min_precision, args.min_recall)
    picked = chosen or closest
    passed = chosen is not None

    out = {"model": model_ref, "task": args.task, "positive_label": pos_label,
          "bar": {"min_precision": args.min_precision, "min_recall": args.min_recall},
          "n_val": len(val_rows), "n_test": len(test_rows),
          "swept_threshold": picked["threshold"], "swept_meets_bar": passed}

    def test_point(thr):
        tp, fp, fn, tn = confusion_at(test_golds, test_probs, thr)
        p, r, f1 = prf(tp, fp, fn)
        return {"threshold": thr, "precision": p, "recall": r, "f1": f1,
                "balanced_accuracy": bal_acc(tp, fp, fn, tn), "tp": tp, "fp": fp, "fn": fn, "tn": tn}

    out["test_at_swept"] = test_point(picked["threshold"])
    out["test_at_fixed"] = {str(t): test_point(t) for t in (0.5, 0.6, 0.7)}

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        tp = out["test_at_swept"]
        print(f"model={model_ref} task={args.task} pos={pos_label} bar=P>={args.min_precision}/R>={args.min_recall}")
        print(f"  val-swept thr={tp['threshold']:.2f} (bar {'MET' if passed else 'NOT MET on val -- closest reported'})")
        print(f"  test @swept: P={tp['precision']:.2f} R={tp['recall']:.2f} F1={tp['f1']:.2f} "
              f"bal_acc={tp['balanced_accuracy']:.2f} (n={out['n_test']})")
        for t in (0.5, 0.6, 0.7):
            m = out["test_at_fixed"][str(t)]
            print(f"  test @{t}: P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f} bal_acc={m['balanced_accuracy']:.2f}")
    return out


if __name__ == "__main__":
    main()
