"""Per-skill usage and check findings for Skill Tree's nodes.

usage_by_skill()    invocation count and last date per skill, from usage-survey.py --json
findings_by_skill() problems and warnings per skill, from check-skills.zsh

Both are cached. The survey walks every transcript, so its result is kept until the newest
transcript mtime changes (re-checked at most every CHECK_TTL seconds); the check is cheap but is
keyed the same way on the newest SKILL.md mtime. Pack skills are keyed "pack:skill", the name
they are invoked by; flat skills by their plain name.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CHECK_TTL = 30.0


def parse_usage(survey: dict) -> dict:
    """Combine Skill-tool invocations ("skills") and typed /slash prompts ("slash")."""
    out: dict = {}
    for counts, lasts in ((survey.get("skills") or {}, survey.get("skills_last") or {}),
                          (survey.get("slash") or {}, survey.get("slash_last") or {})):
        for name, n in counts.items():
            rec = out.setdefault(name, {"count": 0, "last": None})
            rec["count"] += int(n)
            day = (lasts.get(name) or "")[:10] or None
            if day and (rec["last"] is None or day > rec["last"]):
                rec["last"] = day
    return out


def skill_key(path: str) -> str | None:
    """'claude/skills/x/SKILL.md' -> 'x'; 'claude/skills/p/skills/x/SKILL.md' -> 'p:x'.
    None for anything that is not under a skill (rules, commands, a pack's own dir)."""
    parts = path.strip().split("/")
    if len(parts) < 3 or parts[:2] != ["claude", "skills"]:
        return None
    rest = parts[2:]
    if len(rest) >= 3 and rest[1] in ("skills", "off"):
        return f"{rest[0]}:{rest[2]}"
    return rest[0]


def parse_findings(text: str) -> dict:
    """`!! path: what` are problems, `-- path: what` warnings; attached to the skill under path."""
    out: dict = {}
    for line in text.splitlines():
        if line[:3] not in ("!! ", "-- "):
            continue
        path, sep, what = line[3:].partition(": ")
        key = skill_key(path) if sep else None
        if key is None:
            continue
        bucket = out.setdefault(key, {"problems": [], "warnings": []})
        bucket["problems" if line.startswith("!!") else "warnings"].append(f"{path}: {what}")
    return out


def _projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


def _newest(paths) -> float:
    best = 0.0
    for p in paths:
        try:
            best = max(best, p.stat().st_mtime)
        except OSError:
            pass
    return best


def _transcripts_mtime() -> float:
    return _newest(_projects_dir().glob("*/*.jsonl"))


def _skills_mtime() -> float:
    return _newest((ROOT / "claude" / "skills").glob("**/SKILL.md"))


class _Cached:
    def __init__(self, key, compute):
        self.key, self.compute = key, compute
        self.sig = self.value = None
        self.checked = 0.0

    def get(self):
        now = time.monotonic()
        if self.value is not None and now - self.checked < CHECK_TTL:
            return self.value
        sig = self.key()
        if self.value is None or sig != self.sig:
            self.value, self.sig = self.compute(), sig
        self.checked = now
        return self.value


def _run_survey() -> dict:
    try:
        r = subprocess.run([sys.executable, str(HERE / "usage-survey.py"), "--json"],
                           capture_output=True, text=True, timeout=300)
        return parse_usage(json.loads(r.stdout))
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def _run_check() -> dict:
    try:
        r = subprocess.run([str(HERE / "check-skills.zsh")], capture_output=True, text=True,
                           timeout=60)  # exits 1 when there are problems; the text is what counts
        return parse_findings(r.stdout)
    except (OSError, subprocess.SubprocessError):
        return {}


_usage = _Cached(_transcripts_mtime, _run_survey)
_findings = _Cached(_skills_mtime, _run_check)


def usage_by_skill() -> dict:
    """{name: {"count": int, "last": "YYYY-MM-DD"|None}}, recomputed when a transcript changed."""
    return _usage.get()


def findings_by_skill() -> dict:
    """{name: {"problems": [...], "warnings": [...]}}, only skills that have any."""
    return _findings.get()
