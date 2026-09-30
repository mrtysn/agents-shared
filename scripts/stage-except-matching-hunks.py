#!/usr/bin/env python3
# DESC: Stage a file's working-tree changes except the hunks another session made, picked by regex
"""Stage a file's working-tree changes except some hunks.

    stage-except-matching-hunks.py FILE --exclude REGEX [--exclude REGEX…] [--dry-run]

Splits `git diff -U0 FILE` into hunks; the hunks whose changed lines match an
exclude regex are someone else's. The staged blob is the working file with
those hunks reversed (patch -R), so every other change is staged and theirs
stay only in the working tree.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--exclude", action="append", default=[])
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

diff = subprocess.run(["git", "diff", "-U0", "--", args.file], capture_output=True, text=True, check=True).stdout
head, hunks, cur = [], [], None
for line in diff.splitlines(keepends=True):
    if line.startswith("@@"):
        cur = [line]
        hunks.append(cur)
    elif cur is None:
        head.append(line)
    else:
        cur.append(line)
theirs = []
for h in hunks:
    bad = [rx for rx in args.exclude if re.search(rx, "".join(h[1:]))]
    print(("SKIP " if bad else "KEEP ") + h[0].strip()[:100], file=sys.stderr)
    if bad:
        theirs.append(h)
with open(args.file) as f:
    text = f.read()
with tempfile.TemporaryDirectory() as tmp:
    copy = os.path.join(tmp, "f")
    with open(copy, "w") as f:
        f.write(text)
    if theirs:
        patch = "".join(head) + "".join("".join(h) for h in theirs)
        subprocess.run(["patch", "-R", "-s", "-u", copy], input=patch, text=True, check=True)
    if args.dry_run:
        subprocess.run(["git", "diff", "--no-index", "--stat", args.file, copy])
        sys.exit(0)
    sha = subprocess.run(["git", "hash-object", "-w", copy], capture_output=True, text=True, check=True).stdout.strip()
mode = "100755" if os.access(args.file, os.X_OK) else "100644"
subprocess.run(["git", "update-index", "--cacheinfo", f"{mode},{sha},{args.file}"], check=True)
