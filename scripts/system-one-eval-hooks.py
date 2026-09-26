#!/usr/bin/env python3
# DESC: Score one system-one checkpoint (or the base) on every hook's test split with thresholds swept on val, through system-one-measure.py
"""
system-one-eval-hooks: the per-hook bar numbers for one model, on the held-out test
split, with every threshold chosen on the val split first and applied once.

Runs scripts/system-one-measure.py (so the state, the questions file and the Router
load path are exactly the hook's) four times per hook where a threshold is involved:
  bash    val --sweep picks the gate thresholds (recall >= 0.95 at lowest false-ask,
          else max recall minus false-ask); test at those thresholds reports the gate's
          recall on should-ask rows and false-ask rate on benign rows (bar 0.95 / 0.10)
  prompt  test accuracy of the kind choice (no threshold)
  stop    test precision/recall of "padded" at --stop-threshold on needless_table (the
          val best-F1 threshold system-one-train.py writes to eval.json, read from
          --model-dir/eval.json when present; the file's gate otherwise). The
          deterministic rule's 0.42/0.82 is the bar.
  ask     val best-F1 threshold per question; test precision/recall per question at it

Prints one line per hook and, with --json, the full per-hook summaries.

Usage (system-one venv's python):
    system-one-eval-hooks.py --splits ~/.local/state/system-one/train/splits.json
                             [--model-dir DIR] [--stop-threshold T] [--device mps] [--json]
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MEASURE = os.path.join(HERE, "system-one-measure.py")


def run(args, hook, split, extra):
    cmd = [sys.executable, MEASURE, "--hook", hook, "--device", args.device, "--splits", args.splits,
           "--split", split, "--json"] + extra
    if args.model_dir:
        cmd += ["--model-dir", args.model_dir]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"{' '.join(cmd)}\n{res.stderr[-2000:]}")
    return json.loads(res.stdout)


def fmt(x):
    return "nan" if x != x else f"{x:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--splits", required=True, help="splits.json from system-one-train-data.py")
    ap.add_argument("--model-dir", default=None, help="fine-tuned checkpoint dir; omit for the base model")
    ap.add_argument("--stop-threshold", type=float, default=None,
                    help="needless_table threshold for the stop hook (default: val threshold from "
                         "--model-dir/eval.json, else the questions file's gate)")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = {}
    label = args.model_dir or "base"

    # bash: sweep on val, apply to test
    val = run(args, "bash", "val", ["--sweep"])
    thr = val["sweep"]["chosen"]["thresholds"]
    test = run(args, "bash", "test", ["--thresholds", json.dumps(thr)])
    o = test["overall"]
    out["bash"] = {"val_thresholds": thr, "val_chosen": val["sweep"]["chosen"], "test": o}
    print(f"bash    n={test['n']} recall={fmt(o['recall'])} false_ask={fmt(o['false_ask_rate'])} "
          f"(bar 0.95/0.10) thresholds={json.dumps(thr)}")

    # prompt: accuracy
    test = run(args, "prompt", "test", [])
    out["prompt"] = {"test": {"accuracy": test["accuracy"], "per_class": test["per_class"]}}
    print(f"prompt  n={test['n']} accuracy={test['accuracy']:.3f} " +
          " ".join(f"{c}:R={fmt(m['recall'])}" for c, m in test["per_class"].items()))

    # stop: val threshold from eval.json, applied to test
    stop_thr = args.stop_threshold
    if stop_thr is None and args.model_dir and os.path.exists(os.path.join(args.model_dir, "eval.json")):
        with open(os.path.join(args.model_dir, "eval.json"), encoding="utf-8") as f:
            stop_thr = json.load(f).get("thresholds", {}).get("stop/needless_table")
    extra = ["--thresholds", json.dumps({"needless_table": stop_thr})] if stop_thr is not None else []
    test = run(args, "stop", "test", extra)
    pc = test["per_class"].get("padded", {"precision": float("nan"), "recall": float("nan")})
    out["stop"] = {"threshold": stop_thr, "test": {"accuracy": test["accuracy"], "padded": pc}}
    print(f"stop    n={test['n']} padded P={fmt(pc['precision'])} R={fmt(pc['recall'])} acc={test['accuracy']:.3f} "
          f"thr={stop_thr if stop_thr is not None else 'file'} (rule bar 0.42/0.82)")

    # ask: best-F1 threshold per question on val, applied to test
    val = run(args, "ask", "val", [])
    thr = {q: (m["best"]["threshold"] if m["best"]["threshold"] is not None else m["threshold"])
           for q, m in val["per_question"].items()}
    test = run(args, "ask", "test", ["--thresholds", json.dumps(thr)])
    out["ask"] = {"val_thresholds": thr, "test": test["per_question"]}
    print(f"ask     n={test['n']} " + "  ".join(
        f"{q}: P={fmt(m['precision'])} R={fmt(m['recall'])} (pos {m['n_pos']}, thr {thr[q]:.2f})"
        for q, m in test["per_question"].items()))

    if args.json:
        print(json.dumps({"model": label, **out}, indent=2))


if __name__ == "__main__":
    main()
