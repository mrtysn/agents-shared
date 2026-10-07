#!/usr/bin/env python3
# DESC: Copy upstream skills into agents-shared as external skills (files, pristine .upstream base, source.json)
"""
Vendor one or more skills from GitHub into this repo as external skills, the way the manual steps
in CLAUDE.md ("Adding a new external skill") describe, in one go:

  claude/skills/<name>/                     a flat skill, or
  claude/skills/<group>/skills/<name>/      a skill inside an existing group
    <every file under the skill's upstream directory>
    .upstream/<the same files>              pristine base for the 3-way merge in sync-external-skills.sh
    source.json                             repo, path, files, commit, updated

One blobless clone per upstream repo (then a single batched fetch of the skill directories),
paced by --delay seconds; the first failed git command stops all further contact with GitHub.

Usage:
    scripts/vendor-upstream-skill.py <owner/repo> <path/to/SKILL.md> (--group NAME | --flat) [--dry-run]
    scripts/vendor-upstream-skill.py --plan plan.json [--dry-run]

plan.json is [{"repo": "...", "path": ".../SKILL.md", "dest": "<group>" | "flat"}, ...].
Prints one JSON object per skill on stdout. Refuses a skill whose SKILL.md sits at the repo root
(its directory is the whole repo), more than 500 files or 20 MB, and an existing destination.

Environment: VENDOR_GIT_BASE overrides https://github.com (used by the tests, which clone local repos).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MAX_FILES = 500
MAX_BYTES = 20 * 1024 * 1024


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s -> %s" % (" ".join(cmd[:3]), r.stderr.strip()[:300]))
    return r.stdout


def destination(root, dest, name):
    skills = os.path.join(root, "claude", "skills")
    if dest == "flat":
        return os.path.join(skills, name)
    if not os.path.isdir(os.path.join(skills, dest, "skills")):
        raise ValueError("no such group: %s" % dest)
    return os.path.join(skills, dest, "skills", name)


def vendor_repo(root, repo, entries, base):
    """entries: list of (path, dest). Returns one result dict per entry."""
    results = []
    work = tempfile.mkdtemp(prefix="vendor-")
    d = os.path.join(work, "repo")
    run(["git", "clone", "-q", "--depth=1", "--filter=blob:none", "--no-checkout",
         "%s/%s.git" % (base, repo), d])
    sha = run(["git", "rev-parse", "HEAD"], cwd=d).strip()
    dirs = []
    for path, dest in entries:
        sdir = os.path.dirname(path)
        if sdir in ("", "."):
            results.append({"repo": repo, "path": path, "ok": False,
                            "error": "SKILL.md at the repo root: its directory is the whole repo"})
            continue
        dirs.append((path, dest, sdir))
    if dirs:
        run(["git", "sparse-checkout", "set", "--cone"] + sorted({x[2] for x in dirs}), cwd=d)
        run(["git", "checkout", "-q"], cwd=d)
    for path, dest, sdir in dirs:
        res = {"repo": repo, "path": path, "dest": dest}
        try:
            name = os.path.basename(sdir)
            target = destination(root, dest, name)
            if os.path.exists(target):
                raise ValueError("already exists: %s" % os.path.relpath(target, root))
            listing = run(["git", "ls-tree", "-r", "HEAD", "--", sdir], cwd=d).strip().split("\n")
            files, total = [], 0
            for line in listing:
                meta, rel = line.split("\t", 1)
                mode = meta.split()[0]
                files.append((rel[len(sdir) + 1:], mode))
                total += os.path.getsize(os.path.join(d, rel))
            if not files or not any(f == "SKILL.md" for f, _ in files):
                raise ValueError("no SKILL.md under %s" % sdir)
            if len(files) > MAX_FILES or total > MAX_BYTES:
                raise ValueError("too large (%d files, %.1f MB); vendor by hand" % (len(files), total / 1048576))
            res.update({"name": name, "target": os.path.relpath(target, root), "files": len(files), "ok": True})
            res["_plan"] = (target, sdir, files)
        except (ValueError, OSError, RuntimeError) as e:
            res.update({"ok": False, "error": str(e)})
        results.append(res)
    res_by_path = {r["path"]: r for r in results}
    return sha, d, res_by_path, work


def write_skill(d, repo, path, sha, plan):
    target, sdir, files = plan
    os.makedirs(target)
    for rel, mode in files:
        src = os.path.join(d, sdir, rel)
        for out in (os.path.join(target, rel), os.path.join(target, ".upstream", rel)):
            os.makedirs(os.path.dirname(out), exist_ok=True)
            shutil.copyfile(src, out)
            if mode == "100755":
                os.chmod(out, 0o755)
    source = {"repo": repo, "path": path, "files": sorted(r for r, _ in files), "commit": sha,
              "updated": datetime.date.today().isoformat()}
    with open(os.path.join(target, "source.json"), "w", encoding="utf-8") as f:
        json.dump(source, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?")
    ap.add_argument("path", nargs="?")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--group")
    g.add_argument("--flat", action="store_true")
    ap.add_argument("--plan", help="JSON file: [{repo, path, dest}]")
    ap.add_argument("--dry-run", action="store_true", help="clone and check, write nothing")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--root", default=DEFAULT_ROOT, help="agents-shared checkout (default: this one)")
    args = ap.parse_args()

    if args.plan:
        plan = json.load(open(args.plan, encoding="utf-8"))
    elif args.repo and args.path and (args.group or args.flat):
        plan = [{"repo": args.repo, "path": args.path, "dest": "flat" if args.flat else args.group}]
    else:
        ap.error("give <repo> <path> with --group/--flat, or --plan")

    base = os.environ.get("VENDOR_GIT_BASE", "https://github.com")
    by_repo, seen, out = {}, set(), []
    for e in plan:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", e["repo"]) or not e["path"].endswith("SKILL.md"):
            out.append({"repo": e["repo"], "path": e["path"], "ok": False,
                        "error": "expected <owner/repo> and a path ending in SKILL.md"})
            continue
        if (e["repo"], e["path"]) in seen:
            out.append({"repo": e["repo"], "path": e["path"], "ok": False, "error": "listed twice in the plan"})
            continue
        seen.add((e["repo"], e["path"]))
        by_repo.setdefault(e["repo"], []).append((e["path"], e["dest"]))

    failed_git = False
    for n, (repo, entries) in enumerate(by_repo.items()):
        if failed_git:
            out += [{"repo": repo, "path": p, "ok": False, "error": "skipped after an earlier git failure"} for p, _ in entries]
            continue
        if n:
            time.sleep(args.delay)
        try:
            sha, d, results, work = vendor_repo(args.root, repo, entries, base)
        except RuntimeError as e:
            failed_git = True
            out += [{"repo": repo, "path": p, "ok": False, "error": "git failed, no further requests: %s" % e} for p, _ in entries]
            continue
        for r in results.values():
            planned = r.pop("_plan", None)
            if planned and not args.dry_run:
                try:
                    write_skill(d, repo, r["path"], sha, planned)
                except OSError as e:
                    r.update({"ok": False, "error": str(e)})
            r["commit"] = sha
            out.append(r)
        shutil.rmtree(work, ignore_errors=True)

    for r in out:
        print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if all(r.get("ok") for r in out) else 1)


if __name__ == "__main__":
    main()
