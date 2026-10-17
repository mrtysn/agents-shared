#!/usr/bin/env python3
# DESC: Show each optional skill group's recent use, the folders that used it, and whether it loads globally and in a repo
"""
report-skill-group-use: For every skill group installed under ~/.claude/skills (a folder with
.claude-plugin/plugin.json, loaded by Claude Code as the plugin <group>@skills-dir), print its
skill count, how often its skills ran in the last N days (typed as /group:skill or invoked by
the model), which folders they ran in, and whether the group is on globally and in a repo.

A group with no entry in enabledPlugins is on. ~/.claude/settings.json sets the global state;
a repo's .claude/settings.json and .claude/settings.local.json override it there.

Uses come from agents-shared's scripts/extract-session-text.py over every transcript, sub-agents
included. A 30-day run takes about 20 seconds.

Examples:
  report-skill-group-use.py                     # global state, last 30 days
  report-skill-group-use.py --repo .            # plus this repo's state
  report-skill-group-use.py --days 90 --json
"""

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = Path.home() / ".claude" / "skills"


def groups():
    """{group: skill count} for every skill group under ~/.claude/skills."""
    out = {}
    for manifest in sorted(SKILLS.glob("*/.claude-plugin/plugin.json")):
        g = manifest.parent.parent
        out[g.name] = len(list(g.glob("skills/*/SKILL.md")))
    return out


def enabled(settings_files):
    """{plugin key: bool} merged over settings files, later files winning."""
    state = {}
    for f in settings_files:
        try:
            state.update(json.loads(Path(f).read_text()).get("enabledPlugins", {}))
        except (OSError, json.JSONDecodeError):
            pass
    return state


def uses(days):
    """{group: Counter(folder)} of skill runs in the last `days` days."""
    rows = subprocess.run(
        [sys.executable, str(HERE / "extract-session-text.py"), "--all", "--days", str(days), "--subagents",
         "--kinds", "user,calls", "--json", "--max-chars", "160",
         "--grep", r"(^|<command-name>/?)[a-z][a-z0-9-]*:[a-z]"],
        capture_output=True, text=True, check=True).stdout
    found = collections.defaultdict(collections.Counter)
    for line in rows.splitlines():
        r = json.loads(line)
        names = []
        if r.get("label") == "CALL Skill" and r.get("text"):
            names = [r["text"].split()[0]]
        elif r.get("group") == "user":
            names = re.findall(r"<command-name>/?([\w-]+:[\w-]+)</command-name>", r.get("text") or "")
        folder = Path(r.get("cwd") or r.get("project") or "?").name
        for n in names:
            found[n.split(":")[0]][folder] += 1
    return found


def main():
    ap = argparse.ArgumentParser(description="Recent use and on/off state of each optional skill group.")
    ap.add_argument("--days", type=int, default=30, help="look back this many days (default 30)")
    ap.add_argument("--repo", help="also report the group's state in this repo")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = ap.parse_args()

    found = uses(a.days)
    glob_state = enabled([Path.home() / ".claude" / "settings.json"])
    repo = Path(a.repo).resolve() if a.repo else None
    repo_state = enabled([repo / ".claude" / "settings.json", repo / ".claude" / "settings.local.json"]) if repo else {}

    rows = []
    for g, n in groups().items():
        key = f"{g}@skills-dir"
        on = glob_state.get(key, True)
        rows.append({"group": g, "skills": n, "uses": sum(found[g].values()),
                     "folders": dict(found[g].most_common()), "global": on,
                     "repo": repo_state.get(key, on) if repo else None,
                     "repo_choice_recorded": key in repo_state if repo else None})
    rows.sort(key=lambda r: -r["uses"])
    if a.json:
        print(json.dumps({"days": a.days, "repo": str(repo) if repo else None, "groups": rows}))
        return
    print(f"Skill groups, uses in the last {a.days} days" + (f", state in {repo.name}" if repo else ""))
    for r in rows:
        state = ("on" if r["global"] else "off") + (f" / here {'on' if r['repo'] else 'off'}" if repo else "")
        where = ", ".join(f"{k} {v}" for k, v in list(r["folders"].items())[:5]) or "-"
        print(f"  {r['group']:<10} {r['skills']:>2} skills  {r['uses']:>4} uses  {state:<16} {where}")


if __name__ == "__main__":
    main()
