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

Usage:
  sync-skill-group-settings.py [--config DIR] [--dry-run] [--quiet]
      DIR defaults to $CLAUDE_CONFIG_DIR, else ~/.claude.
"""

import argparse
import json
import os
import shutil
import sys
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


def main():
    ap = argparse.ArgumentParser(description="Write the committed skill-group defaults into settings.json.")
    ap.add_argument("--config", type=Path,
                    default=Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"))
    ap.add_argument("--dry-run", action="store_true", help="say what would change, write nothing")
    ap.add_argument("--quiet", action="store_true", help="print only changes")
    a = ap.parse_args()

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
