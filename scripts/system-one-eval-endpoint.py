#!/usr/bin/env python3
# DESC: Score a Kev/Laya /v1/systemone endpoint against the system-one-train-data.py held-out rows
"""
system-one-eval-endpoint: score any /v1/systemone-compatible server (Kev-0.8B,
Kev-4B, a fine-tuned checkpoint, or the base Laya server) against one split of
the train.jsonl scripts/system-one-train-data.py writes, so different arms
(base model, a Kev size, a fine-tune) can be compared on exactly the same rows.

Each JSONL row is one (state, single question) pair, already carrying the gold
label as a string ("true"/"false" for noul, the option name for choice, the
level's 0-based index as a string for score -- see that script's docstring).
This script converts the row's internal question shape ({"t", "ins", "crit"})
to the request shape the endpoint expects ({"type", "instructions", "criteria"})
and POSTs {"state": row["state"], "questions": {row["question_name"]: q}} --
one row per request, sent sequentially (never in parallel; the server is
local and single-threaded model work does not benefit from concurrent
requests here).

For every task in the split it reports:
  - noul questions: precision/recall/F1 at a threshold, plus accuracy.
    --split val sweeps every distinct predicted probability for the best-F1
    threshold per (task, question_name) and can write it with --save-thresholds;
    --split test loads exactly those thresholds back with --thresholds so the
    two runs are comparable one-shot, no peeking at test to pick a cutoff.
  - choice questions: accuracy (argmax vs label) and per-class recall.

Prints one summary table and writes a JSON report (--out, or stdout only with
none given).

Usage:
    system-one-eval-endpoint.py --data train.jsonl --split val \\
        --endpoint http://127.0.0.1:7812/v1/systemone \\
        --save-thresholds kev-0.8b-val-thresholds.json --out kev-0.8b-val.json

    system-one-eval-endpoint.py --data train.jsonl --split test \\
        --endpoint http://127.0.0.1:7812/v1/systemone \\
        --thresholds kev-0.8b-val-thresholds.json --out kev-0.8b-test.json
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def to_request_question(q: dict) -> dict:
    """Internal shape ({"t", "ins", "crit"}, as system-one-train-data.py stores it,
    built with laya.Agent._to_internal) -> the /v1/systemone request shape
    ({"type", "instructions", "criteria"}). laya's own _to_internal is the exact
    inverse of this for noul/choice, so no information is lost."""
    return {"type": q["t"], "instructions": q["ins"], "criteria": q.get("crit")}


def load_rows(data_path: str, split: str, task: str | None) -> list:
    rows = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("split") != split:
                continue
            if task and row.get("task") != task:
                continue
            rows.append(row)
    return rows


def post(endpoint: str, model: str, state, question: dict, qname: str, timeout: float):
    body = json.dumps({"state": state, "model": model,
                       "questions": {qname: to_request_question(question)}}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={"content-type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read())
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return out, elapsed_ms


def run_split(rows: list, endpoint: str, model: str, timeout: float, verbose: bool, retries: int) -> tuple:
    """POST every row sequentially. Returns (records, skipped): one record per
    answered row (task, question_name, type, label (gold string), and either
    p_true (noul) or choice+probabilities), plus a list of rows a request kept
    failing for after `retries` attempts (e.g. a transient 500 from a server
    under load elsewhere) -- skipped rather than aborting the whole split, since
    those are the exception, not the rule."""
    records, skipped = [], []
    n = len(rows)
    for i, row in enumerate(rows):
        qname = row["question_name"]
        q = row["question"]
        resp = err = None
        for attempt in range(retries + 1):
            try:
                resp, ms = post(endpoint, model, row["state"], q, qname, timeout)
                err = None
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                err = e
                if attempt < retries:
                    time.sleep(1.0 * (attempt + 1))
        if err is not None:
            print(f"  request {i + 1}/{n} ({row['task']}/{qname}) failed after {retries + 1} attempts: {err} -- skipping", file=sys.stderr)
            skipped.append({"task": row["task"], "question_name": qname, "error": str(err)})
            continue
        ans = resp["answers"].get(qname)
        if ans is None:
            print(f"  request {i + 1}/{n} ({row['task']}/{qname}): no answer for {qname!r} in response -- skipping", file=sys.stderr)
            skipped.append({"task": row["task"], "question_name": qname, "error": "no answer in response"})
            continue
        rec = {"task": row["task"], "question_name": qname, "type": q["t"], "label": row["label"], "latency_ms": ms}
        if q["t"] == "noul":
            rec["p_true"] = float(ans["noul"])
        elif q["t"] == "choice":
            rec["choice"] = ans.get("choice")
            rec["probabilities"] = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
        elif q["t"] == "score":
            rec["score"] = float(ans.get("score", 0.0))
            rec["probabilities"] = {k: float(v) for k, v in (ans.get("probabilities") or {}).items()}
        records.append(rec)
        if verbose and (i + 1) % 25 == 0:
            print(f"  {i + 1}/{n} done", file=sys.stderr)
    return records, skipped


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * p * r / (p + r) if (tp and p + r) else 0.0
    return p, r, f1


def best_threshold(pairs: list) -> dict:
    """Sweep every distinct predicted probability for the threshold with the best F1."""
    best = {"threshold": 0.5, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    for thr in sorted({round(p, 4) for _, p in pairs}):
        tp = sum(1 for g, p in pairs if g and p >= thr)
        fp = sum(1 for g, p in pairs if not g and p >= thr)
        fn = sum(1 for g, p in pairs if g and p < thr)
        prec, rec, f1 = prf(tp, fp, fn)
        if f1 >= best["f1"]:
            best = {"threshold": thr, "precision": prec, "recall": rec, "f1": f1}
    return best


def score_noul_group(recs: list, threshold: float | None) -> dict:
    pairs = [(r["label"] == "true", r["p_true"]) for r in recs]
    swept = best_threshold(pairs)
    thr = threshold if threshold is not None else swept["threshold"]
    tp = sum(1 for g, p in pairs if g and p >= thr)
    fp = sum(1 for g, p in pairs if not g and p >= thr)
    fn = sum(1 for g, p in pairs if g and p < thr)
    tn = sum(1 for g, p in pairs if not g and p < thr)
    precision, recall, f1 = prf(tp, fp, fn)
    accuracy = (tp + tn) / len(pairs) if pairs else float("nan")
    return {"type": "noul", "n": len(pairs), "threshold": thr, "threshold_swept": swept["threshold"],
            "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def score_choice_group(recs: list) -> dict:
    classes = sorted({r["label"] for r in recs} | {r["choice"] for r in recs if r.get("choice") is not None})
    confusion = {g: {p: 0 for p in classes} for g in classes}
    label_probs = []
    correct = 0
    for r in recs:
        pred = r.get("choice")
        gold = r["label"]
        if pred is not None:
            confusion[gold][pred] += 1
            if pred == gold:
                correct += 1
        label_probs.append(r.get("probabilities", {}).get(gold, 0.0))
    per_class = {}
    for c in classes:
        tp = confusion[c][c]
        fn = sum(confusion[c].values()) - tp
        fp = sum(confusion[g][c] for g in classes if g != c)
        per_class[c] = {"n": sum(confusion[c].values()),
                        "recall": tp / (tp + fn) if (tp + fn) else float("nan"),
                        "precision": tp / (tp + fp) if (tp + fp) else float("nan")}
    accuracy = correct / len(recs) if recs else float("nan")
    mean_label_prob = sum(label_probs) / len(label_probs) if label_probs else float("nan")
    return {"type": "choice", "n": len(recs), "accuracy": accuracy, "mean_label_probability": mean_label_prob,
            "per_class": per_class, "confusion": confusion}


def group_and_score(records: list, thresholds: dict) -> dict:
    """thresholds: {task: {question_name: float}}, or {} to sweep every noul group
    on this split. Returns {task: {question_name: metrics}}."""
    groups = {}
    for r in records:
        groups.setdefault(r["task"], {}).setdefault(r["question_name"], []).append(r)
    out = {}
    for task, by_q in groups.items():
        out[task] = {}
        for qname, recs in by_q.items():
            if recs[0]["type"] == "noul":
                thr = thresholds.get(task, {}).get(qname)
                out[task][qname] = score_noul_group(recs, thr)
            elif recs[0]["type"] == "choice":
                out[task][qname] = score_choice_group(recs)
            else:
                out[task][qname] = {"type": recs[0]["type"], "n": len(recs), "note": "scoring not implemented for 'score' questions"}
    return out


def extract_thresholds(scored: dict) -> dict:
    return {task: {qname: m["threshold"] for qname, m in by_q.items() if m["type"] == "noul"}
            for task, by_q in scored.items()}


def print_table(scored: dict, latencies: list) -> None:
    print(f"{'task':<14}{'question':<26}{'type':<8}{'n':>5}{'thr':>6}{'P':>7}{'R':>7}{'F1':>7}{'acc':>7}")
    for task in sorted(scored):
        for qname, m in sorted(scored[task].items()):
            if m["type"] == "noul":
                print(f"{task:<14}{qname:<26}{'noul':<8}{m['n']:>5}{m['threshold']:>6.2f}"
                      f"{m['precision']:>7.2f}{m['recall']:>7.2f}{m['f1']:>7.2f}{m['accuracy']:>7.2f}")
            elif m["type"] == "choice":
                print(f"{task:<14}{qname:<26}{'choice':<8}{m['n']:>5}{'':>6}{'':>7}{'':>7}{'':>7}{m['accuracy']:>7.2f}")
                for c, pc in sorted(m["per_class"].items()):
                    print(f"{'':<14}  {c:<24}{'':<8}{pc['n']:>5}{'':>6}{pc['precision']:>7.2f}{pc['recall']:>7.2f}")
            else:
                print(f"{task:<14}{qname:<26}{m['type']:<8}{m['n']:>5}  (unscored)")
    if latencies:
        lat = sorted(latencies)
        p50 = lat[len(lat) // 2]
        p95 = lat[int(round(0.95 * (len(lat) - 1)))]
        print(f"\nlatency ms: p50={p50:.1f} p95={p95:.1f} n={len(lat)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--data", required=True, help="train.jsonl written by system-one-train-data.py")
    ap.add_argument("--split", required=True, choices=["train", "val", "test"], help="which split's rows to score")
    ap.add_argument("--task", help="restrict to one task (bash/prompt/stop/ask/outstanding); default all tasks in the file")
    ap.add_argument("--endpoint", required=True, help="POST URL, e.g. http://127.0.0.1:7812/v1/systemone")
    ap.add_argument("--model", default="kev-latest", help="model field sent in each request (default: kev-latest)")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-request HTTP timeout in seconds")
    ap.add_argument("--thresholds", metavar="FILE",
                    help="JSON {task: {question_name: threshold}} to apply (e.g. from a prior --save-thresholds "
                         "run on --split val); noul groups not listed fall back to sweeping this split")
    ap.add_argument("--save-thresholds", metavar="FILE",
                    help="write the best-F1 threshold swept per (task, question_name) noul group to this file")
    ap.add_argument("--out", metavar="FILE", help="write the full JSON report here (also always printed as a table)")
    ap.add_argument("--retries", type=int, default=2,
                    help="retries (1s, 2s, ... backoff) for a request that errors before skipping that row "
                         "(default 2; a local server sharing a GPU with other work can 500 transiently)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print progress every 25 requests")
    args = ap.parse_args()

    rows = load_rows(args.data, args.split, args.task)
    if not rows:
        sys.exit(f"no rows for split={args.split!r} task={args.task!r} in {args.data}")

    thresholds = {}
    if args.thresholds:
        with open(args.thresholds, encoding="utf-8") as f:
            thresholds = json.load(f)

    print(f"scoring {len(rows)} rows from {args.data} split={args.split} "
          f"task={args.task or 'all'} against {args.endpoint} (model={args.model})", file=sys.stderr)
    records, skipped = run_split(rows, args.endpoint, args.model, args.timeout, args.verbose, args.retries)
    if not records:
        sys.exit(f"every request failed ({len(skipped)}/{len(rows)}); nothing to score")
    if skipped:
        print(f"\n{len(skipped)}/{len(rows)} rows skipped after repeated request failures (see above)", file=sys.stderr)

    scored = group_and_score(records, thresholds)
    print_table(scored, [r["latency_ms"] for r in records])

    if args.save_thresholds:
        with open(args.save_thresholds, "w", encoding="utf-8") as f:
            json.dump(extract_thresholds(scored), f, indent=2)
        print(f"\nwrote thresholds -> {args.save_thresholds}", file=sys.stderr)

    report = {"data": args.data, "split": args.split, "task": args.task, "endpoint": args.endpoint,
              "model": args.model, "n_rows": len(rows), "n_scored": len(records), "skipped": skipped, "scored": scored,
              "latency_ms": {"p50": sorted(r["latency_ms"] for r in records)[len(records) // 2] if records else None}}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"wrote report -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
