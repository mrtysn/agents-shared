#!/usr/bin/env python3
# DESC: Fine-tune the Laya decision model on the system-one JSONL, calibrate on val, sweep thresholds, evaluate on test, save an Agent-loadable checkpoint
"""
system-one-train: supervised fine-tune of the base Laya English checkpoint on the
JSONL system-one-train-data.py builds, temperature-calibrate on the val split, sweep
a per-question decision threshold on val, evaluate on the test split at those
thresholds, and save a checkpoint directory laya.Agent can load.

Loss: class-weighted soft-label cross-entropy between log_softmax(logits) over the
marker positions (laya.common.DecisionModel.forward already masks non-option logits
to -1e4, and the one-hot target is 0 there) and the row's target. Rows are grouped
into units (task/question_name); with --class-weight balanced (the default) each
unit's classes are weighted n_unit / (K * n_class), capped at --max-class-weight, so
a unit with 20% positives cannot be solved by always answering its majority class.
The batch loss is the weight-normalised mean. act_head gets no gradient (nothing in
the loss reads it) and is frozen besides.

--freeze-encoder trains only head (the small TransformerEncoder on top), type_emb and
scorer, with the encoder run detached. Without it, the encoder trains too at
--lr-encoder against --lr-head for the rest, optionally under --amp autocast (off by
default: fp32 measured faster than bf16 on MPS and keeps the scorer's logit precision),
with --grad-checkpoint for ModernBERT's layers and the head (required for an unfrozen
run in 32 GB: 9 GB peak at batch 8 with it, 20 GB and swapping without). AdamW with
--weight-decay on matrices only (never biases, norms or embeddings), linear warmup
over --warmup of the steps then linear decay, gradient clipping at --clip.

Selection: every --eval-every optimizer steps (and at each epoch end) the val split
is scored per unit; the checkpoint kept is the one with the best mean over tasks of
that task's mean unit balanced accuracy (macro recall at argmax, so a collapse to
the majority class scores 0.5 rather than the base rate), ties by lower mean loss.

After training: temperatures per temp_bucket(qtype, k) present in val (LBFGS on one
scalar, clamped with laya.common.clamp_temperature; every entry written is clamped),
then for each noul unit the P(true) threshold (after that temperature, i.e. the same
number the hook reads as .noul) with the best val F1, then the test split scored per
unit at that threshold and at 0.5. Everything lands in train.log, in <out>/eval.json,
and in rl_agent_config.json's "training.finetune" block (val thresholds included).
--eval-only runs only that last part on an existing checkpoint (the base id or any
directory), so base / head-only / full can be compared on identical rows.

Output layout matches what laya.Agent(dir) loads: model.safetensors (the trained
DecisionModel's state_dict, same keys as the base checkpoint, fp32), rl_agent_config.json
(base config with temperatures + training block updated), tokenizer/ and encoder/
copied verbatim from the base snapshot. The last step loads the saved directory with
laya.Agent and checks its answers against the trainer's own probabilities on val rows.

Runs fully offline: HF_HUB_OFFLINE=1 is set before laya is imported, and the base
checkpoint is loaded from the local hub cache (no network call). Needs no pip installs
beyond the system-one venv.

Usage:
    system-one-train.py --name full-v1 [--data FILE] [--out DIR] [--base ID|DIR]
        [--freeze-encoder] [--epochs 6] [--batch 8] [--lr-encoder 2e-5] [--lr-head 1e-4]
        [--warmup 0.1] [--weight-decay 0.01] [--clip 1.0] [--amp none|bf16|fp16]
        [--grad-checkpoint] [--eval-every N] [--class-weight balanced|none]
        [--max-class-weight 10] [--device mps|cpu] [--limit N] [--seed 0]
    system-one-train.py --eval-only --base DIR|ID --name label [--out DIR]
"""
import argparse
import json
import math
import os
import random
import shutil
import sys
import time
import traceback

DEFAULT_DATA = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state"),
                            "system-one", "train", "train.jsonl")
DEFAULT_MODELS_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share"),
                                  "system-one", "models")
BASE_MODEL_ID = "convaiinnovations/laya"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_rows(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def unit_of(row: dict) -> str:
    return f"{row['task']}/{row.get('question_name') or 'q'}"


def encode_row(tok, row: dict, max_len: int, head_max_len: int):
    from laya.common import build_sequence, QTYPES
    q = row["question"]
    ids, markers = build_sequence(tok, row["state"], q, max_len, head_max_len)
    target = row["target"]
    if len(markers) != len(target):
        return None  # an option was truncated out by head_max_len; drop the row
    return {"ids": ids, "markers": markers, "qtype": QTYPES[q["t"]], "target": target,
            "task": row["task"], "unit": unit_of(row), "gold": int(max(range(len(target)), key=target.__getitem__))}


def encode_rows(tok, rows, max_len, head_max_len):
    out = []
    for r in rows:
        it = encode_row(tok, r, max_len, head_max_len)
        if it is not None:
            out.append(it)
    return out



def write_config(out_dir: str, cfg: dict) -> None:
    """Write rl_agent_config.json atomically (temp file + os.replace): a crash
    mid-write must never leave the checkpoint with a truncated config, since the
    post-calibration rewrite replaces the only copy."""
    final = os.path.join(out_dir, "rl_agent_config.json")
    tmp = final + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, final)

def batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def class_weights(items: list, mode: str, cap: float) -> dict:
    """unit -> list of per-class weights (index = option index)."""
    counts = {}
    for it in items:
        c = counts.setdefault(it["unit"], [0] * len(it["target"]))
        c[it["gold"]] += 1
    weights = {}
    for unit, c in counts.items():
        n = sum(c)
        present = [x for x in c if x > 0]
        if mode == "none":
            weights[unit] = [1.0] * len(c)
        else:
            weights[unit] = [min(cap, n / (len(present) * x)) if x > 0 else 0.0 for x in c]
    return weights, counts


def forward_batch(model, items, device, pad_id, detach_encoder: bool, amp_dtype=None):
    import torch
    from laya.common import collate_items
    c = collate_items([[it] for it in items], pad_id)
    kw = {k: c[k].to(device) for k in ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")}
    target = c["target"].to(device)
    if amp_dtype is not None:
        with torch.autocast(device_type=device.type, dtype=amp_dtype):
            logits, _act = model(kw["input_ids"], kw["attention_mask"], kw["marker_pos"], kw["marker_mask"],
                                 kw["qtype"], detach_encoder=detach_encoder)
    else:
        logits, _act = model(kw["input_ids"], kw["attention_mask"], kw["marker_pos"], kw["marker_mask"],
                             kw["qtype"], detach_encoder=detach_encoder)
    logits = logits.float()
    per_row = -(target * torch.log_softmax(logits, dim=-1)).sum(-1)
    return logits, per_row, c


def weighted_loss(per_row, items, weights):
    import torch
    w = torch.tensor([weights[it["unit"]][it["gold"]] for it in items], dtype=per_row.dtype, device=per_row.device)
    return (w * per_row).sum() / w.sum().clamp_min(1e-6)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if (tp and p + r) else 0.0
    return p, r, f


def best_threshold(pairs: list) -> dict:
    """Best-F1 threshold over (gold_bool, score) pairs, swept over every distinct score
    (the same rule scripts/system-one-measure.py's best_threshold applies)."""
    best = {"threshold": 0.5, "precision": float("nan"), "recall": 0.0, "f1": 0.0, "fires": 0}
    for thr in sorted({round(s, 3) for _, s in pairs}):
        tp = sum(1 for g, s in pairs if g and s >= thr)
        fp = sum(1 for g, s in pairs if not g and s >= thr)
        fn = sum(1 for g, s in pairs if g and s < thr)
        p, r, f1 = prf(tp, fp, fn)
        if f1 > best["f1"]:
            best = {"threshold": thr, "precision": p, "recall": r, "f1": f1, "fires": tp + fp}
    return best


def score_split(model, items, device, pad_id, batch_size, temps=None):
    """Per-unit logits/targets over a split (fp32, no autocast: the hook's single-row
    inference path). Returns unit -> {"logits": [...], "gold": [...], "probs": [...] (temperature-scaled)}."""
    import numpy as np
    import torch
    from laya.common import temp_bucket
    model.eval()
    out = {}
    with torch.no_grad():
        for chunk in batched(items, batch_size):
            logits, per_row, c = forward_batch(model, chunk, device, pad_id, detach_encoder=False)
            logits = logits.cpu().numpy()
            for i, it in enumerate(chunk):
                k = len(it["markers"])
                z = logits[i, :k].astype(np.float64)
                if temps is not None:
                    t = temps["by_options"].get(temp_bucket(it["qtype"], k), temps["by_qtype"][it["qtype"]])
                    z = z / t
                p = np.exp(z - z.max())
                p = p / p.sum()
                u = out.setdefault(it["unit"], {"task": it["task"], "logits": [], "gold": [], "probs": [],
                                                "loss": [], "k": k, "qtype": it["qtype"]})
                u["logits"].append(logits[i, :k].tolist())
                u["gold"].append(it["gold"])
                u["probs"].append(p.tolist())
                u["loss"].append(float(per_row[i]))
    model.train()
    return out


def unit_metrics(u: dict, threshold=None) -> dict:
    """acc, balanced acc (macro recall over gold classes present), mean loss, and for
    two-option units P/R/F1 of option 1 (true) at argmax and, when given, at threshold."""
    gold = u["gold"]
    pred = [max(range(len(p)), key=p.__getitem__) for p in u["probs"]]
    n = len(gold)
    acc = sum(1 for g, p in zip(gold, pred) if g == p) / n
    classes = sorted(set(gold))
    recalls = [sum(1 for g, p in zip(gold, pred) if g == c and p == c) / sum(1 for g in gold if g == c) for c in classes]
    m = {"n": n, "acc": acc, "bal_acc": sum(recalls) / len(recalls), "loss": sum(u["loss"]) / n,
         "per_class_recall": {str(c): r for c, r in zip(classes, recalls)}}
    if u["k"] == 2:
        s = [p[1] for p in u["probs"]]
        for tag, thr in (("at_0.5", 0.5), ("at_thr", threshold)):
            if thr is None:
                continue
            tp = sum(1 for g, v in zip(gold, s) if g == 1 and v >= thr)
            fp = sum(1 for g, v in zip(gold, s) if g == 0 and v >= thr)
            fn = sum(1 for g, v in zip(gold, s) if g == 1 and v < thr)
            p, r, f = prf(tp, fp, fn)
            m[tag] = {"threshold": thr, "precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn,
                      "tn": n - tp - fp - fn, "n_pos": tp + fn}
    return m


def selection_score(scored: dict):
    """(mean over tasks of mean unit balanced accuracy, mean loss)."""
    by_task = {}
    for unit, u in scored.items():
        m = unit_metrics(u)
        by_task.setdefault(u["task"], []).append((m["bal_acc"], m["loss"]))
    task_bal = [sum(b for b, _ in v) / len(v) for v in by_task.values()]
    task_loss = [sum(l for _, l in v) / len(v) for v in by_task.values()]
    return (sum(task_bal) / len(task_bal) if task_bal else 0.0,
            sum(task_loss) / len(task_loss) if task_loss else float("inf"))


def fit_temperature(logits_list, target_idx):
    """One scalar t minimising NLL of softmax(logits/t) on (n, k) logits. LBFGS on log(t).

    Rows may have different option counts (a temp_bucket such as choice:11+ spans k=11..17):
    each row is right-padded to the batch's max width with the same -1e4 sentinel
    DecisionModel.forward already uses to mask non-option logits, so padded columns get ~0
    softmax mass and never compete with the row's real options."""
    import numpy as np
    import torch
    PAD_LOGIT = -1e4
    k_max = max(len(row) for row in logits_list)
    padded = np.full((len(logits_list), k_max), PAD_LOGIT, dtype=np.float64)
    for i, row in enumerate(logits_list):
        padded[i, :len(row)] = row
    logits = torch.tensor(padded, dtype=torch.float32)
    target = torch.zeros_like(logits)
    target[torch.arange(len(target_idx)), torch.tensor(target_idx)] = 1.0
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=50, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        lp = torch.log_softmax(logits / log_t.exp(), dim=-1)
        loss = -(target * lp).sum(-1).mean()
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().item())


def fit_temperatures(scored: dict, cfg: dict, tee) -> dict:
    """Per temp_bucket and per qtype on the val split's raw logits; buckets with under
    3 items keep the checkpoint's value. Every value written is clamped."""
    from laya.common import temp_bucket, clamp_temperature, QTYPE_NAMES
    by_bucket, by_qtype = {}, {}
    for u in scored.values():
        b = temp_bucket(u["qtype"], u["k"])
        by_bucket.setdefault(b, ([], [])); by_qtype.setdefault(u["qtype"], ([], []))
        for lg, g in zip(u["logits"], u["gold"]):
            by_bucket[b][0].append(lg); by_bucket[b][1].append(g)
            by_qtype[u["qtype"]][0].append(lg); by_qtype[u["qtype"]][1].append(g)
    tbo = {k: clamp_temperature(v) for k, v in cfg.get("temperature_by_options", {}).items()}
    for b, (lg, g) in by_bucket.items():
        if len(lg) < 3:
            tee(f"  {b}: only {len(lg)} val items, keeping base temperature"); continue
        tbo[b] = clamp_temperature(fit_temperature(lg, g))
        tee(f"  {b}: n={len(lg)} temperature={tbo[b]:.4f}")
    temperature = [clamp_temperature(t) for t in cfg.get("temperature", [1.0, 1.0, 1.0])]
    for qt, (lg, g) in by_qtype.items():
        if len(lg) < 3:
            continue
        # a qtype pools buckets of different k; fit it on the largest-k bucket's rows only when
        # widths are mixed, since padding logits across widths is not a temperature fit
        widths = {len(x) for x in lg}
        if len(widths) == 1:
            temperature[qt] = clamp_temperature(fit_temperature(lg, g))
            tee(f"  qtype {QTYPE_NAMES[qt]}: n={len(lg)} temperature={temperature[qt]:.4f}")
    return {"by_options": tbo, "by_qtype": temperature}


def evaluate_and_sweep(model, val_items, test_items, device, pad_id, batch, temps, tee):
    """Val: per-unit metrics and best-F1 threshold. Test: per-unit metrics at that threshold."""
    val = score_split(model, val_items, device, pad_id, batch, temps)
    thresholds, report = {}, {"val": {}, "test": {}, "thresholds": {}}
    tee("val split, thresholds swept per unit (noul: best-F1 on P(true) after temperature):")
    for unit in sorted(val):
        u = val[unit]
        thr = None
        if u["k"] == 2:
            b = best_threshold([(g == 1, p[1]) for g, p in zip(u["gold"], u["probs"])])
            thr = b["threshold"]
            thresholds[unit] = thr
        m = unit_metrics(u, thr)
        report["val"][unit] = m
        report["thresholds"][unit] = thr
        line = f"  {unit:<36} n={m['n']:<4} acc={m['acc']:.3f} bal_acc={m['bal_acc']:.3f} loss={m['loss']:.3f}"
        if thr is not None:
            a = m["at_thr"]
            line += f"  thr={thr:.2f} P/R/F1={a['precision']:.2f}/{a['recall']:.2f}/{a['f1']:.2f} (pos {a['n_pos']})"
        tee(line)
    if test_items:
        test = score_split(model, test_items, device, pad_id, batch, temps)
        tee("test split at the val thresholds:")
        for unit in sorted(test):
            u = test[unit]
            m = unit_metrics(u, thresholds.get(unit))
            report["test"][unit] = m
            line = f"  {unit:<36} n={m['n']:<4} acc={m['acc']:.3f} bal_acc={m['bal_acc']:.3f}"
            if "at_thr" in m:
                a, h = m["at_thr"], m["at_0.5"]
                line += (f"  thr={a['threshold']:.2f} P/R/F1={a['precision']:.2f}/{a['recall']:.2f}/{a['f1']:.2f}"
                         f" (pos {a['n_pos']})  @0.5 P/R={h['precision']:.2f}/{h['recall']:.2f}")
            else:
                line += "  recall/class=" + json.dumps({k: round(v, 2) for k, v in m["per_class_recall"].items()})
            tee(line)
    return report, thresholds


def verify_agent(out_dir, device, val_rows, model, tok, pad_id, max_len, head_max_len, temps, tee, n=8):
    """laya.Agent(out_dir) must answer the trainer's val rows with the trainer's own
    temperature-scaled probabilities (the hook reads exactly those numbers)."""
    import laya
    check = laya.Agent(out_dir, device=device)
    items = encode_rows(tok, val_rows[:n], max_len, head_max_len)
    scored = score_split(model, items, torch_device(device), pad_id, 1, temps)
    by_unit_idx = {}
    worst = 0.0
    for r, it in zip(val_rows[:n], items):
        u = scored[it["unit"]]
        i = by_unit_idx.get(it["unit"], 0); by_unit_idx[it["unit"]] = i + 1
        q = r["question"]
        qdef = {"type": q["t"], "instructions": q["ins"]}
        if q.get("crit") is not None:
            qdef["criteria"] = q["crit"]
        ans = check.system_one(r["state"], {"q": qdef})["answers"]["q"]
        if ans.get("noul") is not None:
            agent_p = [1.0 - ans["noul"], ans["noul"]]
        else:
            agent_p = list(ans["probabilities"].values())
        d = max(abs(a - b) for a, b in zip(agent_p, u["probs"][i]))
        worst = max(worst, d)
    tee(f"verify: laya.Agent({out_dir}) vs trainer on {len(items)} val rows, max |dp| = {worst:.5f}")
    if worst > 5e-3:
        tee("verify: FAILED, the saved checkpoint does not reproduce the trainer's probabilities")
        sys.exit(1)


def torch_device(name):
    import torch
    return torch.device(name)


def mps_peak_gb():
    import torch
    if torch.backends.mps.is_available():
        return torch.mps.driver_allocated_memory() / 2 ** 30
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--data", default=DEFAULT_DATA, help="train.jsonl from system-one-train-data.py")
    ap.add_argument("--name", required=True, help="checkpoint name; naming is the caller's call")
    ap.add_argument("--out", default=None,
                    help="output dir (default: $XDG_DATA_HOME/system-one/models/<name>; with --eval-only on a "
                         "local --base dir, that dir)")
    ap.add_argument("--base", default=BASE_MODEL_ID, help="base checkpoint id or local dir")
    ap.add_argument("--eval-only", action="store_true",
                    help="no training: sweep val thresholds and score test for --base as it is")
    ap.add_argument("--freeze-encoder", action="store_true")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr-encoder", type=float, default=2e-5)
    ap.add_argument("--lr-head", type=float, default=1e-4)
    ap.add_argument("--warmup", type=float, default=0.1, help="fraction of steps for linear warmup")
    ap.add_argument("--weight-decay", type=float, default=0.01)
    ap.add_argument("--clip", type=float, default=1.0, help="gradient-norm clip (0 disables)")
    ap.add_argument("--amp", choices=["bf16", "fp16", "none"], default="none",
                    help="autocast dtype for the training forward (eval is always fp32). Measured on MPS "
                         "with --grad-checkpoint: fp32 is faster than bf16 (3.7 vs 5.2 s/step at batch 8, "
                         "9 GB either way) and bf16 rounds the scorer logits coarsely, so fp32 is the default")
    ap.add_argument("--grad-checkpoint", action="store_true",
                    help="checkpoint ModernBERT's layers and the head; needed for an unfrozen run on 32 GB "
                         "(fp32 batch 8 peaks at 9 GB with it, 20 GB and swapping without)")
    ap.add_argument("--eval-every", type=int, default=0,
                    help="also evaluate (and keep the best) every N optimizer steps; 0 = epoch ends only")
    ap.add_argument("--class-weight", choices=["balanced", "none"], default="balanced")
    ap.add_argument("--max-class-weight", type=float, default=10.0)
    ap.add_argument("--device", choices=["mps", "cpu"], default="mps")
    ap.add_argument("--limit", type=int, default=0, help="cap train rows (val/test to a fifth of it): smoke tests")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.out:
        out_dir = args.out
    elif args.eval_only and os.path.isdir(args.base):
        out_dir = args.base
    else:
        out_dir = os.path.join(DEFAULT_MODELS_DIR, args.name)
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, "eval.log" if args.eval_only else "train.log")
    log_file = open(log_path, "a", encoding="utf-8")

    def tee(msg):
        log(msg)
        log_file.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        log_file.flush()

    os.environ["HF_HUB_OFFLINE"] = "1"
    random.seed(args.seed)
    import torch
    torch.manual_seed(args.seed)
    import laya

    tee(f"args: {json.dumps(vars(args))}")
    tee(f"loading base checkpoint {args.base!r} on {args.device}")
    agent = laya.Agent(args.base, device=args.device)
    model, tok, cfg = agent.model, agent.tok, agent.cfg
    device = agent.device
    pad_id = tok.pad_token_id
    max_len = cfg.get("max_len", 512)
    head_max_len = cfg.get("head_max_len", 192)

    rows = load_rows(args.data)
    split_rows = {s: [r for r in rows if r["split"] == s] for s in ("train", "val", "test")}
    if args.limit:
        for s, rs in split_rows.items():
            random.Random(args.seed).shuffle(rs)
            split_rows[s] = rs[: (args.limit if s == "train" else max(8, args.limit // 5))]
    tee("encoding rows")
    items = {s: encode_rows(tok, rs, max_len, head_max_len) for s, rs in split_rows.items()}
    tee("rows train/val/test = " + "/".join(str(len(items[s])) for s in ("train", "val", "test")) +
        "  (dropped by head_max_len: " + "/".join(str(len(split_rows[s]) - len(items[s])) for s in ("train", "val", "test")) + ")")

    temps = {"by_options": dict(agent.temperature_by_options), "by_qtype": list(agent.temperature)}
    best_state = None
    if not args.eval_only:
        if args.grad_checkpoint:
            try:
                model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
            except Exception as e:
                tee(f"warning: encoder.gradient_checkpointing_enable() failed: {e}")
            model.head_checkpointing = True
        for p in model.act_head.parameters():
            p.requires_grad_(False)
        if args.freeze_encoder:
            for p in model.encoder.parameters():
                p.requires_grad_(False)

        def groups(named, lr):
            decay = [p for n, p in named if p.requires_grad and p.ndim >= 2]
            no_decay = [p for n, p in named if p.requires_grad and p.ndim < 2]
            return [{"params": decay, "lr": lr, "weight_decay": args.weight_decay},
                    {"params": no_decay, "lr": lr, "weight_decay": 0.0}]

        head_named = (list(model.head.named_parameters()) + list(model.type_emb.named_parameters())
                      + list(model.scorer.named_parameters()))
        param_groups = groups(head_named, args.lr_head)
        if not args.freeze_encoder:
            enc_named = [(n, p) for n, p in model.encoder.named_parameters()]
            # embeddings are matrices but get no decay either
            param_groups += [{"params": [p for n, p in enc_named if p.ndim >= 2 and "embed" not in n],
                              "lr": args.lr_encoder, "weight_decay": args.weight_decay},
                             {"params": [p for n, p in enc_named if p.ndim < 2 or "embed" in n],
                              "lr": args.lr_encoder, "weight_decay": 0.0}]
        param_groups = [g for g in param_groups if g["params"]]
        optimizer = torch.optim.AdamW(param_groups)
        n_trainable = sum(p.numel() for g in param_groups for p in g["params"])
        tee(f"trainable parameters: {n_trainable / 1e6:.1f}M (encoder {'frozen' if args.freeze_encoder else 'unfrozen'})")

        steps_per_epoch = math.ceil(len(items["train"]) / args.batch)
        total_steps = steps_per_epoch * args.epochs
        warmup_steps = int(round(args.warmup * total_steps))

        def lr_lambda(step):
            if step < warmup_steps:
                return (step + 1) / max(1, warmup_steps)
            return max(0.0, (total_steps - step) / max(1, total_steps - warmup_steps))

        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
        weights, counts = class_weights(items["train"], args.class_weight, args.max_class_weight)
        for unit in sorted(weights):
            tee(f"  class weights {unit:<36} counts={counts[unit]} weights={[round(w, 2) for w in weights[unit]]}")
        amp_dtype = {"bf16": torch.bfloat16, "fp16": torch.float16, "none": None}[args.amp]
        if amp_dtype is not None and device.type == "cpu":
            amp_dtype = None

        best = {"step": 0, "epoch": 0, "score": (-1.0, float("inf"))}
        model.train()
        t_start = time.time()
        step = 0
        peak = 0.0
        skipped = 0

        def do_eval(epoch, tag):
            nonlocal best, best_state
            scored = score_split(model, items["val"], device, pad_id, args.batch)
            bal, loss = selection_score(scored)
            per_task = {}
            for unit, u in scored.items():
                m = unit_metrics(u)
                per_task.setdefault(u["task"], []).append(f"{unit.split('/')[1]}={m['bal_acc']:.2f}")
            tee(f"eval {tag}: val mean task bal_acc={bal:.3f} mean loss={loss:.4f}  " +
                "  ".join(f"[{t}: {' '.join(v)}]" for t, v in sorted(per_task.items())))
            if (bal, -loss) > (best["score"][0], -best["score"][1]):
                best = {"step": step, "epoch": epoch, "score": (bal, loss)}
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                tee(f"  new best at {tag} (bal_acc={bal:.3f})")

        for epoch in range(1, args.epochs + 1):
            ep_items = list(items["train"])
            random.Random(args.seed + epoch).shuffle(ep_items)
            t0 = time.time()
            total_loss, n_items = 0.0, 0
            for bi, chunk in enumerate(batched(ep_items, args.batch)):
                optimizer.zero_grad(set_to_none=True)
                _logits, per_row, _c = forward_batch(model, chunk, device, pad_id, args.freeze_encoder, amp_dtype)
                loss = weighted_loss(per_row, chunk, weights)
                if not torch.isfinite(loss):
                    skipped += 1
                    tee(f"  non-finite loss at step {step + 1}, skipping batch: units="
                        f"{sorted({it['unit'] for it in chunk})} lens={[len(it['ids']) for it in chunk]}")
                    if skipped > 5:
                        sys.exit("too many non-finite batches; aborting")
                    optimizer.zero_grad(set_to_none=True)
                    scheduler.step()
                    step += 1
                    continue
                loss.backward()
                if args.clip:
                    torch.nn.utils.clip_grad_norm_([p for g in param_groups for p in g["params"]], args.clip)
                optimizer.step()
                scheduler.step()
                step += 1
                loss_val = loss.item()
                total_loss += loss_val * len(chunk)
                n_items += len(chunk)
                if device.type == "mps":
                    peak = max(peak, mps_peak_gb())
                if bi % 20 == 0:
                    tee(f"  epoch {epoch} step {step}/{total_steps} loss {loss_val:.4f} lr {scheduler.get_last_lr()[0]:.2e}"
                        + (f" mps {mps_peak_gb():.1f}GB" if device.type == "mps" else ""))
                if args.eval_every and step % args.eval_every == 0 and step % steps_per_epoch != 0:
                    do_eval(epoch, f"step {step}")
            tee(f"epoch {epoch}/{args.epochs} done in {time.time() - t0:.1f}s  train_loss={total_loss / max(1, n_items):.4f}"
                + (f"  peak mps {peak:.1f}GB" if device.type == "mps" else ""))
            do_eval(epoch, f"epoch {epoch}")
        wall = time.time() - t_start
        tee(f"training done in {wall / 60:.1f} min, best at epoch {best['epoch']} step {best['step']} "
            f"(val bal_acc {best['score'][0]:.3f})" + (f", peak mps {peak:.1f}GB" if device.type == "mps" else ""))
        model.load_state_dict(best_state)
        model.head_checkpointing = False
        model.eval()

        # Save a loadable checkpoint now, before calibration (which crashed once on an
        # inhomogeneous temp_bucket) or verify can throw away 40+ minutes of training.
        # temperature / temperature_by_options are still the base checkpoint's own (possibly
        # uncalibrated) values here; calibration below overwrites cfg and rewrites this same
        # rl_agent_config.json in place on success. Nothing here is ever undone by a later
        # failure, so a partial run always leaves an agent-loadable directory.
        training_block = dict(cfg.get("training", {}))
        training_block["finetune"] = {
            "name": args.name, "data": os.path.abspath(args.data), "base": args.base,
            "epochs": args.epochs, "best_epoch": best["epoch"], "best_step": best["step"], "batch": args.batch,
            "lr_encoder": args.lr_encoder, "lr_head": args.lr_head, "warmup": args.warmup,
            "weight_decay": args.weight_decay, "clip": args.clip, "amp": args.amp,
            "freeze_encoder": args.freeze_encoder, "grad_checkpoint": args.grad_checkpoint,
            "class_weight": args.class_weight, "max_class_weight": args.max_class_weight,
            "eval_every": args.eval_every, "seed": args.seed, "limit": args.limit, "device": args.device,
            "train_rows": len(items["train"]), "wall_minutes": round(wall / 60, 1),
            "selection": "mean over tasks of mean unit balanced accuracy on val",
            "val_bal_acc": best["score"][0],
            "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "calibrated": False,
        }
        cfg["training"] = training_block

        from huggingface_hub import snapshot_download
        base_dir = args.base if os.path.isdir(args.base) else snapshot_download(
            args.base, allow_patterns=["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"])
        from safetensors.torch import save_file
        state_dict = {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}
        save_file(state_dict, os.path.join(out_dir, "model.safetensors"))
        write_config(out_dir, cfg)
        for sub in ("tokenizer", "encoder"):
            dst = os.path.join(out_dir, sub)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.copytree(os.path.join(base_dir, sub), dst)
        tee(f"saved checkpoint (provisional, base temperatures, not yet calibrated) to {out_dir}")

        try:
            tee("fitting temperatures on val split")
            val_raw = score_split(model, items["val"], device, pad_id, args.batch)
            temps = fit_temperatures(val_raw, cfg, tee)
        except Exception:
            tee(f"WARNING: temperature calibration failed; the checkpoint already saved at {out_dir} "
                "is loadable with laya.Agent but keeps the base (uncalibrated) temperatures:\n"
                + traceback.format_exc())
            log_file.close()
            raise

    try:
        report, thresholds = evaluate_and_sweep(model, items["val"], items["test"], device, pad_id, args.batch, temps, tee)
    except Exception:
        if not args.eval_only:
            tee(f"WARNING: val/test evaluation failed; the checkpoint already saved at {out_dir} "
                "is loadable with laya.Agent and has calibrated temperatures, but no val thresholds "
                "or eval.json were written:\n" + traceback.format_exc())
        log_file.close()
        raise
    report["model"] = args.base if args.eval_only else out_dir
    report["temperatures"] = temps
    with open(os.path.join(out_dir, "eval.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    tee(f"wrote {os.path.join(out_dir, 'eval.json')}")
    if args.eval_only:
        log_file.close()
        return

    cfg["temperature"] = temps["by_qtype"]
    cfg["temperature_by_options"] = temps["by_options"]
    training_block["finetune"]["val_thresholds"] = thresholds
    training_block["finetune"]["val_by_unit"] = {u: {"acc": m["acc"], "bal_acc": m["bal_acc"]} for u, m in report["val"].items()}
    training_block["finetune"]["calibrated"] = True
    write_config(out_dir, cfg)
    tee(f"updated checkpoint config (calibrated temperatures + val thresholds) at {out_dir}")

    try:
        verify_agent(out_dir, args.device, split_rows["val"], model, tok, pad_id, max_len, head_max_len, temps, tee)
    except SystemExit:
        raise
    except Exception:
        tee(f"WARNING: verify_agent failed to run; the checkpoint at {out_dir} is loadable and "
            "calibrated, but was not cross-checked against laya.Agent:\n" + traceback.format_exc())
    log_file.close()


if __name__ == "__main__":
    main()
