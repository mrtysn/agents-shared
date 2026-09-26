#!/usr/bin/env python3
# DESC: Cheapest baseline arm for the system-one comparison -- sentence-embedding + torch logistic regression, scored like system-one-eval-endpoint.py
"""
system-one-embed-baseline: the cheapest baseline arm for the system-one
decision-model comparison. Embeds each row's `state` with a frozen sentence
embedding model (mean-pooled, L2-normalised last hidden state) and trains one
multinomial logistic regression (plain torch nn.Linear + cross-entropy) per
(task, question_name) group -- exactly the grouping
scripts/system-one-eval-endpoint.py uses when it POSTs rows to an endpoint.
Train/val/test come from the `split` field system-one-train-data.py already
wrote onto every row; val sweeps an L2 weight-decay grid and (for noul
questions) a best-F1 threshold, test is scored once with the val-chosen decay
and threshold. Reports are written in exactly system-one-eval-endpoint.py's
JSON shape (score_noul_group / score_choice_group / extract_thresholds are
imported from that script by path so the two arms are scored identically --
this script never edits it) so embed-val.json / embed-val-thresholds.json /
embed-test.json sit next to kev-*.json and laya-base-*.json in --out-dir and
compare directly.

Fully offline (HF_HUB_OFFLINE=1, set before transformers is imported), CPU
only regardless of what the box reports for mps, no pip installs -- only
transformers' AutoTokenizer/AutoModel (sentence-transformers and sklearn are
not required and are never imported).

For stop/outstanding, whose states run up to ~1500 chars (well past the
model's 512-token limit), two truncation strategies are tried on val for that
task's classifier(s) -- plain head truncation vs. head+tail concatenation
(first half + last half of the token budget, dropping the middle) -- and
whichever scores better on val is used for that task's train/val/test
embeddings, with the choice printed. Other tasks' states are short and always
use head truncation.

Usage:
    system-one-embed-baseline.py --data train.jsonl --splits splits.json \\
        --out-dir ~/.local/state/system-one/train/eval \\
        --model sentence-transformers/all-MiniLM-L6-v2 --device cpu
"""
import argparse
import importlib.util
import json
import os
import sys
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

STATE_HOME = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
DEFAULT_TRAIN_DIR = os.path.join(STATE_HOME, "system-one", "train")
DEFAULT_DATA = os.path.join(DEFAULT_TRAIN_DIR, "train.jsonl")
DEFAULT_SPLITS = os.path.join(DEFAULT_TRAIN_DIR, "splits.json")
DEFAULT_OUT_DIR = os.path.join(DEFAULT_TRAIN_DIR, "eval")

LONG_STATE_TASKS = {"stop", "outstanding"}


def load_eval_module():
    """Import scripts/system-one-eval-endpoint.py by path (hyphenated filename)
    to reuse its scoring functions verbatim -- never edited, only imported.
    The same pattern system-one-train-data.py uses for system-one-measure.py.
    realpath, not abspath: the script may run through a ~/bin symlink, and the
    sibling lives next to the real file, not next to the link. Independent of
    the cwd either way."""
    here = os.path.dirname(os.path.realpath(__file__))
    path = os.path.join(here, "system-one-eval-endpoint.py")
    if not os.path.isfile(path):
        sys.exit(f"system-one-embed-baseline: scoring helpers not found: {path}")
    spec = importlib.util.spec_from_file_location("system_one_eval_endpoint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_rows(data_path: str) -> list:
    rows = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------- embedding

def mean_pool(last_hidden_state, attention_mask, torch):
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = (last_hidden_state * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts


def tokenize_head(texts, tokenizer, max_length, torch):
    enc = tokenizer(texts, truncation=True, max_length=max_length, padding=True, return_tensors="pt")
    return enc["input_ids"], enc["attention_mask"]


def tokenize_head_tail(texts, tokenizer, max_length, torch):
    """First half + last half of the token budget, special tokens added by hand,
    dropping whatever falls in the middle."""
    cls_id, sep_id, pad_id = tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id
    budget = max_length - 2
    head_n = budget // 2
    tail_n = budget - head_n
    seqs = []
    for t in texts:
        ids = tokenizer.encode(t, add_special_tokens=False)
        seq = ids if len(ids) <= budget else ids[:head_n] + ids[-tail_n:]
        seqs.append([cls_id] + seq + [sep_id])
    width = max(len(s) for s in seqs)
    input_ids = torch.full((len(seqs), width), pad_id, dtype=torch.long)
    attn = torch.zeros((len(seqs), width), dtype=torch.long)
    for i, s in enumerate(seqs):
        input_ids[i, :len(s)] = torch.tensor(s, dtype=torch.long)
        attn[i, :len(s)] = 1
    return input_ids, attn


def embed_texts(texts: list, tokenizer, model, torch, device: str, strategy: str,
                max_length: int, batch_size: int):
    """Embed a list of (deduplicated) texts, batched, mean-pooled + L2-normalised."""
    out = []
    tokenize = tokenize_head_tail if strategy == "head_tail" else tokenize_head
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            input_ids, attn = tokenize(batch, tokenizer, max_length, torch)
            input_ids, attn = input_ids.to(device), attn.to(device)
            hidden = model(input_ids=input_ids, attention_mask=attn).last_hidden_state
            pooled = mean_pool(hidden, attn, torch)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            out.append(pooled.cpu())
    return torch.cat(out, dim=0) if out else torch.zeros((0, model.config.hidden_size))


def embed_unique_states(rows: list, tokenizer, model, torch, device: str, strategy: str,
                        max_length: int, batch_size: int) -> dict:
    states = sorted({r["state"] for r in rows})
    vecs = embed_texts(states, tokenizer, model, torch, device, strategy, max_length, batch_size)
    return dict(zip(states, vecs))


# --------------------------------------------------------------------- classifier

def class_index(row: dict) -> int:
    return row["target"].index(max(row["target"]))


def train_logreg(X, y, n_classes: int, weight_decay: float, torch, epochs: int = 200, seed: int = 0):
    torch.manual_seed(seed)
    lin = torch.nn.Linear(X.shape[1], n_classes)
    counts = torch.bincount(y, minlength=n_classes).float().clamp(min=1)
    class_weights = counts.sum() / (n_classes * counts)
    loss_fn = torch.nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.LBFGS(lin.parameters(), lr=1.0, max_iter=epochs, line_search_fn="strong_wolfe")

    def closure():
        optimizer.zero_grad()
        logits = lin(X)
        reg = sum((p ** 2).sum() for p in lin.parameters())
        loss = loss_fn(logits, y) + weight_decay * reg
        loss.backward()
        return loss

    optimizer.step(closure)
    return lin


def predict(lin, X, torch):
    with torch.no_grad():
        return torch.softmax(lin(X), dim=1)


def build_records(rows: list, probs, class_names: list, qtype: str) -> list:
    recs = []
    for row, p in zip(rows, probs):
        rec = {"task": row["task"], "question_name": row["question_name"], "type": qtype, "label": row["label"]}
        if qtype == "noul":
            rec["p_true"] = float(p[1])
        else:
            idx = int(p.argmax())
            rec["choice"] = class_names[idx]
            rec["probabilities"] = {c: float(p[i]) for i, c in enumerate(class_names)}
        recs.append(rec)
    return recs


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--data", default=DEFAULT_DATA, help=f"train.jsonl from system-one-train-data.py (default: {DEFAULT_DATA})")
    ap.add_argument("--splits", default=DEFAULT_SPLITS,
                    help=f"splits.json from system-one-train-data.py, for reference/row-count sanity only "
                         f"-- split membership is read from each row's own 'split' field (default: {DEFAULT_SPLITS})")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help=f"where embed-{{val,val-thresholds,test}}.json are written (default: {DEFAULT_OUT_DIR})")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="HF model id, must already be in the local HF cache")
    ap.add_argument("--device", default="cpu", choices=["cpu"], help="CPU only -- a fine-tune elsewhere owns the GPU/mps")
    ap.add_argument("--max-length", type=int, default=512, help="tokenizer truncation length (default: the model's own max, 512)")
    ap.add_argument("--batch-size", type=int, default=64, help="embedding batch size")
    ap.add_argument("--weight-decays", type=float, nargs="+", default=[0.0, 1e-4, 1e-3, 1e-2, 1e-1, 1.0],
                    help="L2 weight-decay grid swept per (task, question_name) group on val")
    ap.add_argument("--epochs", type=int, default=200, help="LBFGS max_iter per fit")
    ap.add_argument("--seed", type=int, default=0, help="torch seed for classifier init")
    args = ap.parse_args()

    t0 = time.perf_counter()
    ee = load_eval_module()

    import torch
    torch.set_num_threads(os.cpu_count() or 1)
    from transformers import AutoModel, AutoTokenizer

    print(f"loading {args.model} (cache-only, cpu) ...", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModel.from_pretrained(args.model)
    model.to(args.device).eval()

    rows = load_rows(args.data)
    if not rows:
        sys.exit(f"no rows in {args.data}")
    if os.path.exists(args.splits):
        with open(args.splits, encoding="utf-8") as f:
            splits_doc = json.load(f)
        for task, sp in splits_doc.items():
            n_rows_here = len({r["row_id"] for r in rows if r["task"] == task})
            n_split = sum(len(v) for v in sp.values())
            if n_rows_here and n_rows_here != n_split:
                print(f"note: {args.splits} lists {n_split} rows for task={task} but train.jsonl has {n_rows_here} distinct row_id", file=sys.stderr)

    by_task = {}
    for r in rows:
        by_task.setdefault(r["task"], []).append(r)

    # ---- pick truncation strategy per task (head vs head+tail), only where it matters
    strategy_by_task = {}
    strategy_notes = []
    for task, task_rows in by_task.items():
        if task not in LONG_STATE_TASKS:
            strategy_by_task[task] = "head"
            continue
        best_strategy, best_f1 = "head", -1.0
        for strategy in ("head", "head_tail"):
            vecs = embed_unique_states(task_rows, tokenizer, model, torch, args.device, strategy,
                                       args.max_length, args.batch_size)
            groups = {}
            for r in task_rows:
                groups.setdefault(r["question_name"], []).append(r)
            f1s = []
            for qname, grows in groups.items():
                train_rows = [r for r in grows if r["split"] == "train"]
                val_rows = [r for r in grows if r["split"] == "val"]
                if not train_rows or not val_rows:
                    continue
                n_classes = len(train_rows[0]["target"])
                X_train = torch.stack([vecs[r["state"]] for r in train_rows])
                y_train = torch.tensor([class_index(r) for r in train_rows], dtype=torch.long)
                X_val = torch.stack([vecs[r["state"]] for r in val_rows])
                lin = train_logreg(X_train, y_train, n_classes, 1e-2, torch, args.epochs, args.seed)
                probs = predict(lin, X_val, torch)
                class_names = sorted({r["label"] for r in grows}, key=lambda c: [r for r in grows if r["label"] == c][0]["target"].index(1.0))
                recs = build_records(val_rows, probs, class_names, val_rows[0]["question"]["t"])
                m = ee.score_noul_group(recs, None) if recs[0]["type"] == "noul" else ee.score_choice_group(recs)
                f1s.append(m.get("f1", m.get("accuracy", 0.0)))
            avg = sum(f1s) / len(f1s) if f1s else 0.0
            if avg > best_f1:
                best_f1, best_strategy = avg, strategy
        strategy_by_task[task] = best_strategy
        strategy_notes.append(f"{task}: {best_strategy} (val score {best_f1:.3f})")

    print("truncation strategy chosen per long-state task:", ", ".join(strategy_notes) or "n/a (no long-state tasks in data)", file=sys.stderr)

    # ---- embed every task's unique states once, with its chosen strategy
    embeddings = {}
    for task, task_rows in by_task.items():
        embeddings[task] = embed_unique_states(task_rows, tokenizer, model, torch, args.device,
                                                strategy_by_task[task], args.max_length, args.batch_size)

    # ---- group by (task, question_name), sweep weight decay on val, score val + test
    groups = {}
    for r in rows:
        groups.setdefault((r["task"], r["question_name"]), []).append(r)

    val_scored, test_scored = {}, {}
    val_records_all, test_records_all = [], []
    wd_notes = []
    for (task, qname), grows in sorted(groups.items()):
        vecs = embeddings[task]
        train_rows = [r for r in grows if r["split"] == "train"]
        val_rows = [r for r in grows if r["split"] == "val"]
        test_rows = [r for r in grows if r["split"] == "test"]
        if not train_rows or not val_rows or not test_rows:
            print(f"skipping {task}/{qname}: missing a split (train={len(train_rows)} val={len(val_rows)} test={len(test_rows)})", file=sys.stderr)
            continue
        qtype = train_rows[0]["question"]["t"]
        n_classes = len(train_rows[0]["target"])
        class_names = sorted({r["label"] for r in grows}, key=lambda c: [r for r in grows if r["label"] == c][0]["target"].index(1.0))

        X_train = torch.stack([vecs[r["state"]] for r in train_rows])
        y_train = torch.tensor([class_index(r) for r in train_rows], dtype=torch.long)
        X_val = torch.stack([vecs[r["state"]] for r in val_rows])
        X_test = torch.stack([vecs[r["state"]] for r in test_rows])

        best_wd, best_metric, best_lin = args.weight_decays[0], -1.0, None
        for wd in args.weight_decays:
            lin = train_logreg(X_train, y_train, n_classes, wd, torch, args.epochs, args.seed)
            probs = predict(lin, X_val, torch)
            recs = build_records(val_rows, probs, class_names, qtype)
            m = ee.score_noul_group(recs, None) if qtype == "noul" else ee.score_choice_group(recs)
            metric = m["f1"] if qtype == "noul" else m["accuracy"]
            if metric > best_metric:
                best_metric, best_wd, best_lin = metric, wd, lin
        wd_notes.append(f"{task}/{qname}: wd={best_wd:g} (val {'f1' if qtype == 'noul' else 'acc'}={best_metric:.3f})")

        val_probs = predict(best_lin, X_val, torch)
        val_recs = build_records(val_rows, val_probs, class_names, qtype)
        vm = ee.score_noul_group(val_recs, None) if qtype == "noul" else ee.score_choice_group(val_recs)
        val_scored.setdefault(task, {})[qname] = vm
        val_records_all += val_recs

        test_probs = predict(best_lin, X_test, torch)
        test_recs = build_records(test_rows, test_probs, class_names, qtype)
        thr = vm["threshold"] if qtype == "noul" else None
        tm = ee.score_noul_group(test_recs, thr) if qtype == "noul" else ee.score_choice_group(test_recs)
        test_scored.setdefault(task, {})[qname] = tm
        test_records_all += test_recs

    elapsed = time.perf_counter() - t0

    os.makedirs(args.out_dir, exist_ok=True)
    thresholds = ee.extract_thresholds(val_scored)
    thr_path = os.path.join(args.out_dir, "embed-val-thresholds.json")
    with open(thr_path, "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)

    def report(split, scored, records):
        n = len(records)
        return {"data": args.data, "split": split, "task": None, "endpoint": f"embed:{args.model}",
                "model": args.model, "n_rows": n, "n_scored": n, "skipped": [], "scored": scored,
                "latency_ms": {"p50": None}}

    val_report = report("val", val_scored, val_records_all)
    test_report = report("test", test_scored, test_records_all)
    with open(os.path.join(args.out_dir, "embed-val.json"), "w", encoding="utf-8") as f:
        json.dump(val_report, f, indent=2)
    with open(os.path.join(args.out_dir, "embed-test.json"), "w", encoding="utf-8") as f:
        json.dump(test_report, f, indent=2)

    print("\n=== val ===")
    ee.print_table(val_scored, [])
    print("\n=== test ===")
    ee.print_table(test_scored, [])
    print(f"\nweight-decay choices: {'; '.join(wd_notes)}", file=sys.stderr)
    print(f"wrote {thr_path}", file=sys.stderr)
    print(f"wrote {os.path.join(args.out_dir, 'embed-val.json')}", file=sys.stderr)
    print(f"wrote {os.path.join(args.out_dir, 'embed-test.json')}", file=sys.stderr)
    print(f"wall time: {elapsed:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
