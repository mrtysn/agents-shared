#!/usr/bin/env python3
"""
skill-budget: Audit how Claude Code skills consume the system-prompt skill listing budget.

Scans skills and slash-commands from user-level (~/.claude), the current
project's .claude directory, and installed plugins. Parses each SKILL.md /
command frontmatter, measures description + when_to_use length, and reports
against:

  - The per-skill 1,536-char hard cap (each skill is truncated individually)
  - The total skill-listing budget (default 1% of context, controlled by
    skillListingBudgetFraction in settings.json or SLASH_COMMAND_TOOL_CHAR_BUDGET)

The doctor notice "Skill listing will be truncated / N descriptions dropped"
appears when total exceeds budget. This script tells you which skills are the
biggest contributors and which (if any) are bumping the per-skill cap.

Note: built-in Claude Code skills (init, review, security-review, claude-api,
loop, schedule, etc.) are bundled in the native binary and not visible on disk.
They are listed at the bottom as "unmeasured (built-in)" for completeness.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

PER_SKILL_CAP = 1536  # documented hard cap per skill (description + when_to_use)
DEFAULT_BUDGET_FRACTION = 0.01

# Built-ins we know exist but can't read from disk; surface them so the user
# isn't surprised by the gap between on-disk total and doctor-reported size.
BUILTIN_SKILLS = [
    "init", "review", "security-review", "claude-api",
    "update-config", "keybindings-help", "simplify",
    "fewer-permission-prompts", "loop", "schedule",
]


def parse_frontmatter(path: Path) -> dict:
    """Return YAML frontmatter as a dict. Handles multi-line scalar values."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    out, cur_key, cur_val = {}, None, []
    for line in m.group(1).split("\n"):
        kv = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if kv and not line.startswith((" ", "\t")):
            if cur_key is not None:
                out[cur_key] = "\n".join(cur_val).strip()
            cur_key, cur_val = kv.group(1), [kv.group(2)]
        elif cur_key is not None:
            cur_val.append(line)
    if cur_key is not None:
        out[cur_key] = "\n".join(cur_val).strip()
    return out


def discover(cwd: Path) -> list[dict]:
    home = Path.home()
    sources: list[tuple[str, Path, str]] = []  # (kind, glob_root, source_label)

    sources.append(("skill", home / ".claude" / "skills", "user"))
    sources.append(("command", home / ".claude" / "commands", "user"))

    project_skills = cwd / ".claude" / "skills"
    project_commands = cwd / ".claude" / "commands"
    if project_skills.exists():
        sources.append(("skill", project_skills, "project"))
    if project_commands.exists():
        sources.append(("command", project_commands, "project"))

    # Plugin skills (skill-only, plugin commands are surfaced differently)
    plugins_root = home / ".claude" / "plugins"
    if plugins_root.exists():
        for skill_md in plugins_root.rglob("skills/*/SKILL.md"):
            sources.append(("skill_file", skill_md, "plugin"))

    rows: list[dict] = []
    seen_real: set[str] = set()

    for kind, p, label in sources:
        if kind == "skill":
            files = sorted(p.glob("*/SKILL.md"))
        elif kind == "command":
            files = sorted(p.glob("*.md"))
        elif kind == "skill_file":
            files = [p]
        else:
            continue

        for f in files:
            real = str(f.resolve())
            if real in seen_real:
                continue
            seen_real.add(real)
            fm = parse_frontmatter(f)
            name = fm.get("name") or (
                f.parent.name if f.name == "SKILL.md" else f.stem
            )
            desc = fm.get("description", "")
            wtu = fm.get("when_to_use", "")
            total = len(desc) + len(wtu)
            rows.append({
                "name": name,
                "source": label,
                "kind": "skill" if f.name == "SKILL.md" else "command",
                "path": str(f),
                "desc_chars": len(desc),
                "wtu_chars": len(wtu),
                "total_chars": total,
                "over_cap": total > PER_SKILL_CAP,
            })
    return rows


def fmt_pct(n: int, d: int) -> str:
    if d <= 0:
        return "—"
    return f"{(n / d) * 100:.1f}%"


def render_table(rows: list[dict], context_tokens: int, budget_fraction: float) -> str:
    # Approximate: 1 token ≈ 4 chars. Budget is in chars.
    budget_chars = int(context_tokens * 4 * budget_fraction)
    total = sum(r["total_chars"] for r in rows)

    lines = []
    name_w = max(4, min(34, max((len(r["name"]) for r in rows), default=4)))
    src_w = 7
    kind_w = 7

    header = (
        f"{'name':<{name_w}}  {'source':<{src_w}}  {'kind':<{kind_w}}  "
        f"{'desc':>5}  {'wtu':>4}  {'total':>5}  {'%cap':>5}  flag"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for r in rows:
        flag = ""
        if r["over_cap"]:
            flag = "OVER-CAP"
        elif r["total_chars"] > PER_SKILL_CAP * 0.9:
            flag = "near-cap"
        lines.append(
            f"{r['name'][:name_w]:<{name_w}}  "
            f"{r['source']:<{src_w}}  "
            f"{r['kind']:<{kind_w}}  "
            f"{r['desc_chars']:>5}  "
            f"{r['wtu_chars']:>4}  "
            f"{r['total_chars']:>5}  "
            f"{fmt_pct(r['total_chars'], PER_SKILL_CAP):>5}  "
            f"{flag}"
        )

    lines.append("-" * len(header))
    lines.append(
        f"{'TOTAL':<{name_w}}  {'':<{src_w}}  {'':<{kind_w}}  "
        f"{'':>5}  {'':>4}  {total:>5}"
    )

    over_cap_count = sum(1 for r in rows if r["over_cap"])
    near_cap_count = sum(1 for r in rows if not r["over_cap"] and r["total_chars"] > PER_SKILL_CAP * 0.9)

    lines.append("")
    lines.append(f"Skills/commands measured: {len(rows)}")
    lines.append(f"Total description chars:  {total}")
    lines.append(f"Per-skill cap:            {PER_SKILL_CAP}")
    lines.append(f"  exceeding cap:          {over_cap_count}")
    lines.append(f"  within 10% of cap:      {near_cap_count}")
    lines.append(
        f"Budget ({budget_fraction*100:g}% of {context_tokens:,} tokens "
        f"≈ {budget_chars:,} chars): used {fmt_pct(total, budget_chars)}"
    )
    if total > budget_chars:
        lines.append(f"  OVER BUDGET by {total - budget_chars} chars — descriptions will be trimmed")
    else:
        lines.append(f"  under budget by {budget_chars - total} chars — no trim expected from on-disk skills alone")

    lines.append("")
    lines.append("Built-in Claude Code skills (bundled in binary, not measured):")
    lines.append("  " + ", ".join(BUILTIN_SKILLS))
    lines.append(
        "  These also consume budget; if the doctor notice reports more usage "
        "than the total above, the gap is built-ins + listing overhead."
    )

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", "-c", type=int, default=1_000_000,
                    help="context window in tokens (default: 1000000)")
    ap.add_argument("--budget-fraction", "-b", type=float, default=DEFAULT_BUDGET_FRACTION,
                    help=f"skillListingBudgetFraction (default: {DEFAULT_BUDGET_FRACTION})")
    ap.add_argument("--over-cap", action="store_true",
                    help="only show skills exceeding the per-skill 1,536 char cap")
    ap.add_argument("--top", "-n", type=int, default=0,
                    help="limit to top N by total chars (default: all)")
    ap.add_argument("--source", choices=["user", "project", "plugin"],
                    help="filter by source")
    ap.add_argument("--kind", choices=["skill", "command"],
                    help="filter by kind")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of a table")
    args = ap.parse_args()

    rows = discover(Path.cwd())
    rows.sort(key=lambda r: -r["total_chars"])

    if args.source:
        rows = [r for r in rows if r["source"] == args.source]
    if args.kind:
        rows = [r for r in rows if r["kind"] == args.kind]
    if args.over_cap:
        rows = [r for r in rows if r["over_cap"]]
    if args.top > 0:
        rows = rows[: args.top]

    if args.json:
        print(json.dumps({
            "context_tokens": args.context,
            "budget_fraction": args.budget_fraction,
            "per_skill_cap": PER_SKILL_CAP,
            "rows": rows,
            "builtins_unmeasured": BUILTIN_SKILLS,
        }, indent=2))
    else:
        print(render_table(rows, args.context, args.budget_fraction))

    return 0


if __name__ == "__main__":
    sys.exit(main())
