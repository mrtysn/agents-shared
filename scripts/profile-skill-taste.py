#!/usr/bin/env python3
# DESC: Gather the facts a skill-taste profile is inferred from: every installed skill, its source, adaptation and use, and per-repo take/leave counts
"""
profile-skill-taste: Collect, as one JSON document, the evidence of which skills the user keeps,
how they group and adapt them, and which ones they use, so a taste profile can be drafted and then
applied to the unvendored upstream skills.

Per installed skill (claude/skills in this repo): own or vendored, group (or flat), upstream repo and
path, override.patch size, whether disable-model-invocation is set, its description, and how often it
ran in the transcripts (typed as /name or /group:name, or invoked through the Skill tool, sub-agents
included), with the last use.

Per upstream repo: skills vendored, skills not vendored (from the unvendored-skills cache that
catalog-unvendored-skills.py writes), and the ignore lines in external-skills-ignore.txt.

Also: skill directories deleted in git history, and the transcript window the use counts cover.

Uses come from scripts/extract-session-text.py. A full-history run takes a minute or two.

Examples:
  profile-skill-taste.py --out profile-facts.json
  profile-skill-taste.py --days 30 --out profile-facts.json
"""

import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SKILLS = REPO / "claude" / "skills"
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "agents-shared" / "unvendored-skills.json"


def frontmatter(path):
    """{key: value} from a SKILL.md's YAML frontmatter, flat keys only."""
    text = path.read_text(errors="replace")
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            out[k.strip()] = v.strip().strip("\"'")
    return out


def installed():
    """One row per skill directory under claude/skills, groups opened."""
    rows = []
    for skill_md in sorted(SKILLS.glob("**/SKILL.md")):
        rel = skill_md.relative_to(SKILLS).parts
        if ".upstream" in rel or len(rel) not in (2, 4):
            continue
        if len(rel) == 4 and rel[1] != "skills":
            continue
        d = skill_md.parent
        group = rel[0] if len(rel) == 4 else None
        fm = frontmatter(skill_md)
        src = d / "source.json"
        source = json.loads(src.read_text()) if src.exists() else None
        patch = d / "override.patch"
        rows.append({
            "name": d.name,
            "group": group,
            "own": source is None,
            "repo": source and source.get("repo"),
            "upstream_path": source and source.get("path"),
            "files": len(source.get("files", ["SKILL.md"])) if source else None,
            "override_lines": len(patch.read_text(errors="replace").splitlines()) if patch.exists() else 0,
            "model_invocation_off": fm.get("disable-model-invocation") == "true",
            "description": fm.get("description", ""),
        })
    return rows


def uses(names, days):
    """{name: [count, last ISO time]} of runs over the transcripts."""
    alt = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    cmd = [sys.executable, str(HERE / "extract-session-text.py"), "--all", "--subagents",
           "--kinds", "user,calls", "--json", "--max-chars", "160",
           "--grep", rf"(^|<command-name>/?)([a-z0-9-]+:)?({alt})\b"]
    if days:
        cmd += ["--days", str(days)]
    rows = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    found = {}
    for line in rows.splitlines():
        r = json.loads(line)
        hits = []
        if r.get("label") == "CALL Skill" and r.get("text"):
            hits = [r["text"].split()[0]]
        elif r.get("group") == "user":
            hits = re.findall(r"<command-name>/?([\w:-]+)</command-name>", r.get("text") or "")
        for h in hits:
            n = h.split(":")[-1]
            if n in names:
                c = found.setdefault(n, [0, ""])
                c[0] += 1
                c[1] = max(c[1], r.get("time") or "")
    return found


def window():
    out = subprocess.run([sys.executable, str(HERE / "extract-session-text.py"), "--all", "--window"],
                         capture_output=True, text=True, check=True).stdout
    return out.strip()


def deleted():
    """Skill directories whose SKILL.md was deleted, with date and commit subject."""
    log = subprocess.run(["git", "-C", str(REPO), "log", "--diff-filter=D", "--name-only",
                          "--format=@%h %ad %s", "--date=short", "--",
                          "claude/skills/*/SKILL.md", "claude/skills/*/skills/*/SKILL.md"],
                         capture_output=True, text=True, check=True).stdout
    out, head = [], None
    for line in log.splitlines():
        if line.startswith("@"):
            head = line[1:]
        elif line.strip() and ".upstream" not in line:
            sha, date, subject = head.split(" ", 2)
            out.append({"skill": Path(line).parent.name, "date": date, "commit": sha, "subject": subject})
    return out


def ignores():
    path = HERE / "external-skills-ignore.txt"
    return [l.split(None, 1) for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]


def main():
    ap = argparse.ArgumentParser(description="Gather the evidence a skill-taste profile is drawn from.")
    ap.add_argument("--days", type=int, help="count uses over this many days (default: all transcripts)")
    ap.add_argument("--out", help="write the JSON here instead of stdout")
    a = ap.parse_args()

    skills = installed()
    found = uses({s["name"] for s in skills}, a.days)
    for s in skills:
        s["uses"], s["last_used"] = found.get(s["name"], [0, None])

    unvendored = json.loads(CACHE.read_text())["items"] if CACHE.exists() else []
    repos = collections.defaultdict(lambda: {"vendored": [], "not_vendored": 0, "ignore": []})
    for s in skills:
        if s["repo"]:
            repos[s["repo"]]["vendored"].append(s["name"])
    for i in unvendored:
        repos[i["repo"]]["not_vendored"] += 1
    for repo, glob in ignores():
        repos[repo]["ignore"].append(glob)

    doc = {
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "transcripts": window(),
        "use_days": a.days,
        "unvendored_cache": {"path": str(CACHE), "generated": json.loads(CACHE.read_text()).get("generated")
                             if CACHE.exists() else None},
        "skills": skills,
        "repos": dict(sorted(repos.items(), key=lambda kv: -len(kv[1]["vendored"]))),
        "deleted": deleted(),
    }
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
