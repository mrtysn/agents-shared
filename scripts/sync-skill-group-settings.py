#!/usr/bin/env python3
# DESC: Write claude/skill-groups.json's committed group defaults into a config folder's settings.json
"""
sync-skill-group-settings: make a config folder's settings.json carry the committed default for every
skill group, so a group is off on a fresh machine, a public clone or a new config folder exactly as it
is here. Claude Code treats a group nobody names as on; the defaults name every group.

Only keys that are absent are written: a group the owner switched on or off by hand keeps that choice.
A missing settings.json is created. The file is replaced atomically and keeps its mode.

claude/skill-groups.json holds:
  defaults  {group: true|false}, one entry per group under claude/skills/ (check-skills.zsh enforces it)
  splits    {old group: [new groups]}, the record of each group split

--migrate-splits carries each repo's choice across a split, per the README's rule that "the repos
that enable it and use the moved skills enable the new groups too": in every repo directly under
DEV_ROOT whose gitignored .claude/settings.local.json switches a split group on, each new group with
no entry is written true when its skills ran in that repo within the usage cache's window
(scripts/report-skill-group-use.py --write-cache, which counts a run under a group's old name for the
group holding the skill now). An unused new group gets no entry: its committed default keeps it off.
A repo that commits settings.local.json is reported and left alone, and nothing runs when the cache
is missing or older than 7 days.

Usage:
  sync-skill-group-settings.py [--config DIR] [--dry-run] [--quiet]
  sync-skill-group-settings.py --migrate-splits [--dev-root DIR] [--dry-run] [--quiet]
      DIR defaults to $CLAUDE_CONFIG_DIR, else ~/.claude; --dev-root to $DEV_ROOT, else this repo's parent.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS_FILE = ROOT / "claude" / "skill-groups.json"


def load_groups():
    return json.loads(GROUPS_FILE.read_text())


def read_settings(path):
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.strip():
        sys.exit(f"{path} is empty; not rewriting it")
    return json.loads(text)


def write_json(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def apply_defaults(settings, defaults):
    """Add <group>@skills-dir for every group with no entry; return the keys added."""
    plugins = settings.setdefault("enabledPlugins", {})
    added = []
    for group, on in sorted(defaults.items()):
        key = f"{group}@skills-dir"
        if key not in plugins:
            plugins[key] = on
            added.append(key)
    return added


CACHE = Path(os.environ.get("SKILL_GROUP_CACHE") or
             Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "agents-shared" / "skill-group-use.json")


def used_in(cache, group, repo):
    """Runs of `group`'s skills in `repo` or below; the cache keeps the session's folder as recorded,
    so both the given and the symlink-resolved form of the repo path match."""
    roots = {str(repo), str(repo.resolve())}
    for g in cache.get("groups", []):
        if g.get("group") == group:
            return sum(n for folder, n in g.get("folders", {}).items()
                       if any(folder == r or folder.startswith(r + "/") for r in roots))
    return 0


def tracked(repo, rel):
    return subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode == 0


def migrate_splits(dev_root, splits, dry_run, quiet):
    if not CACHE.exists() or time.time() - CACHE.stat().st_mtime > 7 * 86400:
        if not quiet:
            print(f"split migration: skipped, the usage cache {CACHE} is missing or older than 7 days "
                  "(refresh: scripts/report-skill-group-use.py --write-cache)")
        return
    cache = json.loads(CACHE.read_text())
    for path in sorted(dev_root.glob("*/.claude/settings.local.json")):
        repo = path.parent.parent
        settings = read_settings(path)
        plugins = settings.get("enabledPlugins", {})
        added = {}
        for parent, children in splits.items():
            if plugins.get(f"{parent}@skills-dir") is not True:
                continue
            for child in children:
                key = f"{child}@skills-dir"
                if key not in plugins and key not in added and used_in(cache, child, repo) > 0:
                    added[key] = True
        if not added:
            continue
        if tracked(repo, ".claude/settings.local.json"):
            print(f"split migration: {repo.name} commits .claude/settings.local.json; left alone, would add "
                  + ", ".join(f"{k}={str(v).lower()}" for k, v in added.items()))
            continue
        if not dry_run:
            settings.setdefault("enabledPlugins", {}).update(added)
            write_json(path, settings)
        print(f"split migration: {'would add' if dry_run else 'added'} in {repo.name}: "
              + ", ".join(f"{k}={str(v).lower()}" for k, v in added.items()))


def main():
    ap = argparse.ArgumentParser(description="Write the committed skill-group defaults into settings.json.")
    ap.add_argument("--config", type=Path,
                    default=Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))
    ap.add_argument("--migrate-splits", action="store_true",
                    help="carry each repo's choice for a split group over to the new groups")
    ap.add_argument("--dev-root", type=Path, default=Path(os.environ.get("DEV_ROOT") or ROOT.parent))
    ap.add_argument("--dry-run", action="store_true", help="say what would change, write nothing")
    ap.add_argument("--quiet", action="store_true", help="print only changes")
    a = ap.parse_args()

    if a.migrate_splits:
        migrate_splits(a.dev_root, load_groups()["splits"], a.dry_run, a.quiet)
        return

    path = a.config / "settings.json"
    settings = read_settings(path)
    added = apply_defaults(settings, load_groups()["defaults"])
    if added and not a.dry_run:
        a.config.mkdir(parents=True, exist_ok=True)
        write_json(path, settings)
    if added:
        verb = "would add" if a.dry_run else "added"
        print(f"skill-group defaults: {verb} {len(added)} to {path}: {', '.join(added)}")
    elif not a.quiet:
        print(f"skill-group defaults: {path} already names every group")


if __name__ == "__main__":
    main()
