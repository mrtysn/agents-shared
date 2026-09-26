#!/usr/bin/env python3
# DESC: Merge system-one-train-data.py's combined train.jsonl with extra per-task JSONLs (e.g. from system-one-mine-tasks.py), dropping tasks on request, into a new versioned combined file + splits.json
"""
system-one-merge-tasks: build a new combined fine-tune JSONL + splits.json from
an existing combined file (system-one-train-data.py's train.jsonl) plus one or
more extra per-task JSONLs (system-one-mine-tasks.py's skill_route.jsonl,
will_correct.jsonl, delegate.jsonl, or any file sharing the same row schema:
{"task", "split", "row_id", "state", "question", "target", "label", ...}).

splits.json is never read as an input -- it is *derived* from each file's own
row-level "split" field, since both train-data.py and mine-tasks.py already
write that field on every row (row_id is only unique within a task, so the
grouping key throughout is (task, split)). This sidesteps any drift between a
combined train.jsonl and a splits.json that was regenerated separately (e.g.
by a second script writing its own splits.json to the same --out-dir and
overwriting the first one's task entries -- exactly what happened here: check
for this before trusting an existing splits.json's task set against what its
sibling train.jsonl actually contains).

--drop-task removes a task's rows from the BASE file only (repeatable); its
rows stay wherever the base file already lives on disk, untouched -- this
script only ever reads it. An --extra file is never filtered by --drop-task.

Usage:
    system-one-merge-tasks.py --base train.jsonl [--extra skill_route.jsonl]
        [--extra will_correct.jsonl] [--extra delegate.jsonl]
        [--drop-task outstanding] --out train-v2.jsonl --splits-out splits-v2.json
"""
import argparse
import collections
import json
import os
import sys


def read_rows(path: str):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--base", required=True, help="existing combined train.jsonl (system-one-train-data.py output)")
    ap.add_argument("--extra", action="append", default=[], metavar="JSONL",
                    help="additional per-task JSONL to append, repeatable (row schema must match)")
    ap.add_argument("--drop-task", action="append", default=[], dest="drop_tasks", metavar="NAME",
                    help="task name to exclude from --base (repeatable); its rows are left on disk untouched")
    ap.add_argument("--out", required=True, help="combined output JSONL to write (refuses to overwrite --base)")
    ap.add_argument("--splits-out", required=True, help="splits.json to write, derived from every row's own split")
    args = ap.parse_args()

    out_abs = os.path.abspath(args.out)
    base_abs = os.path.abspath(args.base)
    if out_abs == base_abs:
        sys.exit(f"--out must not be the same file as --base ({base_abs}); this script never overwrites v1")

    drop = set(args.drop_tasks)
    sources = [(args.base, None)] + [(p, None) for p in args.extra]

    counts = collections.defaultdict(lambda: collections.Counter())
    splits = collections.defaultdict(lambda: collections.defaultdict(list))
    dropped_counts = collections.Counter()
    n_written = 0

    with open(args.out, "w", encoding="utf-8") as out:
        for path, _ in sources:
            rows = read_rows(path)
            for r in rows:
                task = r.get("task")
                split = r.get("split")
                if task is None or split is None:
                    sys.exit(f"{path}: row missing 'task' or 'split' field: {r}")
                if task in drop and path == args.base:
                    dropped_counts[task] += 1
                    continue
                out.write(json.dumps(r) + "\n")
                n_written += 1
                counts[task][split] += 1
                splits[task][split].append(r["row_id"])

    splits_plain = {task: {split: sorted(ids) for split, ids in by_split.items()}
                    for task, by_split in splits.items()}
    with open(args.splits_out, "w", encoding="utf-8") as f:
        json.dump(splits_plain, f, indent=2)

    print(f"wrote {args.out} ({n_written} rows)")
    print(f"wrote {args.splits_out}")
    for task in sorted(counts):
        c = counts[task]
        print(f"  {task:<12} train/val/test = {c.get('train', 0)}/{c.get('val', 0)}/{c.get('test', 0)}")
    for task in sorted(dropped_counts):
        print(f"  {task:<12} DROPPED (kept on disk, not in --out): {dropped_counts[task]} rows")


if __name__ == "__main__":
    main()
