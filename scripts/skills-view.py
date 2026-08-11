#!/usr/bin/env python3
"""
Launcher-style board for the Claude skills directory.

Renders every skill the way tools/launcher does for OJ: sections, cards, and a
bottom line naming the action. The split is the same one that tool makes —
trial-skill.sh holds all the truth, this only draws `trial-skill.sh list --json`
and prints the command that changes something. Nothing here mutates state, so
the view can never disagree with the directory it describes.

Why a view at all: a trial skill's default fate is to live forever, because
nothing deletes it but the user happening to look. Rather than have a timer
delete things on its own, this makes looking cheap — and puts the cost of
keeping a skill on screen, in tokens, next to the decision to keep it.

Trials are drawn as cards because each one is a pending decision. Managed skills
are drawn as rows because they are not.

Usage:
    ./scripts/skills-view.py            # the board
    ./scripts/skills-view.py --stale    # only what has gone stale
    ./scripts/skills-view.py --all      # managed skills as cards too
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ANSI, matching jira-board.py: 16 colours, no truecolor, so the board keeps the
# terminal's own theme instead of imposing one.
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"

# One colour per group, cycling — the same reasoning as the launcher's four
# section hues: a colour that identifies a source repo at a glance, and means
# nothing beyond that.
GROUP_PALETTE = [CYAN, GREEN, MAGENTA, BLUE]

CARD_W = 24                     # inner width; 4 cards fit a standard 110-col term
CARD_GAP = "  "


def term_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 110


def tokens(chars):
    """Frontmatter cost in tokens. Deliberately the crude chars/4 — the point is
    the order of magnitude, and a real tokenizer would be a dependency."""
    return round(chars / 4)


def fmt_tokens(chars):
    t = tokens(chars)
    return f"{t / 1000:.1f}k" if t >= 1000 else str(t)


def wrap_name(name, width):
    """Wrap a skill name, breaking at hyphens as well as spaces — skill names are
    hyphenated and would otherwise overflow every card."""
    words, cur = [], ""
    for part in name.replace("-", "-\x00").split("\x00"):
        if len(cur) + len(part) <= width:
            cur += part
        else:
            if cur:
                words.append(cur)
            cur = part
    if cur:
        words.append(cur)
    return words or [name[:width]]


def load_state(trial_sh):
    """Every field this draws comes from trial-skill.sh, so the two can never
    drift. Errors are returned rather than raised so the caller reports them the
    same way for a missing script and a broken one."""
    try:
        out = subprocess.run(
            [str(trial_sh), "list", "--json"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"could not run {trial_sh}: {exc}"
    if out.returncode != 0:
        return None, (out.stderr.strip() or f"trial-skill.sh exited {out.returncode}")
    try:
        return json.loads(out.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"trial-skill.sh returned unparseable JSON: {exc}"


def flag_of(skill):
    if skill.get("pinned"):
        return "PINNED"
    if skill.get("stale"):
        return "STALE"
    if skill["kind"] == "untracked":
        return "UNTRACKED"
    return ""


def card_lines(skill, title_rows, show_flag):
    """One card as a list of plain strings, borders included. Colour is applied
    by the caller so width maths never has to see an escape sequence.

    title_rows and show_flag come from the section rather than the card, so every
    card in a section is the same height without any of them reserving space the
    section never uses."""
    inner = CARD_W
    title = wrap_name(skill["name"], inner - 2)[:title_rows]

    idle = skill.get("idle_days")
    age = "—" if idle is None or idle < 0 else f"idle {idle}d"
    cost = fmt_tokens(skill.get("desc_chars", 0)) + "t"

    body = [f"┌{'─' * inner}┐"]
    for line in title:
        body.append(f"│ {line:<{inner - 2}} │")
    for _ in range(title_rows - len(title)):
        body.append(f"│{' ' * inner}│")
    if show_flag:
        body.append(f"│ {flag_of(skill):<{inner - 2}} │")
    body.append(f"│ {age:<{inner - 2 - len(cost) - 1}} {cost} │")
    body.append(f"└{'─' * inner}┘")
    return body


def print_cards(skills, colors):
    """Cards in rows that fit the terminal. Height is decided once for the whole
    section, so a row prints as a fixed block."""
    title_rows = max(len(wrap_name(s["name"], CARD_W - 2)) for s in skills)
    title_rows = min(title_rows, 3)
    show_flag = any(flag_of(s) for s in skills)

    per_row = max(1, (term_width() + len(CARD_GAP)) // (CARD_W + 2 + len(CARD_GAP)))
    for start in range(0, len(skills), per_row):
        chunk = skills[start:start + per_row]
        built = [(card_lines(s, title_rows, show_flag), colors(s)) for s in chunk]
        height = max(len(b) for b, _ in built)
        for row in range(height):
            out = []
            for body, color in built:
                line = body[row] if row < len(body) else " " * (CARD_W + 2)
                out.append(f"{color}{line}{RST}")
            print("  " + CARD_GAP.join(out))
        print()


def print_rows(skills):
    """Managed skills as dotted rows. They are not decisions, so they get the
    least ink that still shows what they cost."""
    width = min(term_width() - 4, 78)
    for s in skills:
        cost = fmt_tokens(s.get("desc_chars", 0))
        tag = "ext" if s.get("external") else "own"
        dots = "." * max(1, width - len(s["name"]) - len(cost) - len(tag) - 4)
        print(f"  {s['name']} {DIM}{dots}{RST} {cost:>5}  {DIM}{tag}{RST}")
    print()


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def section(title, detail, color=WHITE):
    print(f"  {color}{BOLD}{title}{RST}  {DIM}{detail}{RST}")


def main():
    ap = argparse.ArgumentParser(add_help=True, description=__doc__)
    ap.add_argument("--stale", action="store_true", help="only trials past the idle threshold")
    ap.add_argument("--all", action="store_true", help="draw managed skills as cards too")
    args = ap.parse_args()

    trial_sh = Path(__file__).resolve().parent / "trial-skill.sh"
    state, err = load_state(trial_sh)
    if err:
        print(f"{RED}error:{RST} {err}", file=sys.stderr)
        return 1

    skills = state["skills"]
    stale_days = state["stale_days"]
    trials = [s for s in skills if s["kind"] in ("trial", "untracked")]
    managed = [s for s in skills if s["kind"] == "managed"]
    stale = [s for s in trials if s.get("stale")]

    # The footer always reports the whole machine, never the current filter — a
    # --stale run that said "trials are 3% of your frontmatter" would be
    # measuring the filter rather than the problem.
    total_chars = sum(s.get("desc_chars", 0) for s in skills)
    trial_chars = sum(s.get("desc_chars", 0) for s in trials)

    if args.stale:
        trials = stale
        managed = []

    print()
    section("SKILLS",
            f"{len(skills)} installed · ~{fmt_tokens(total_chars)} tokens of frontmatter "
            f"in every session on this machine", YELLOW)
    print(f"  {DIM}{'─' * min(term_width() - 4, 92)}{RST}")
    print()

    # Trials, grouped by source repo. A group is one decision: eleven skills from
    # one commit should not be eleven separate ones.
    groups = {}
    for s in trials:
        groups.setdefault(s.get("group"), []).append(s)

    palette_for = {}
    for i, g in enumerate(sorted(k for k in groups if k)):
        palette_for[g] = GROUP_PALETTE[i % len(GROUP_PALETTE)]

    def color_of(s):
        if s.get("stale"):
            return RED
        if s.get("pinned"):
            return DIM
        return palette_for.get(s.get("group"), YELLOW)

    for g in sorted(groups, key=lambda k: (k is None, k or "")):
        members = sorted(groups[g], key=lambda s: s["name"])
        cost = sum(m.get("desc_chars", 0) for m in members)
        detail = f"{plural(len(members), 'skill')} · ~{fmt_tokens(cost)} tokens"
        if g:
            section(f"TRIALS · {g}", detail, palette_for[g])
        else:
            section("TRIALS · ungrouped", detail, YELLOW)
        print()
        print_cards(members, color_of)
        if g:
            print(f"  {DIM}→ trial-skill.sh rm --group {g}{RST}"
                  f"{DIM} removes all {len(members)}{RST}")
            print(f"  {DIM}→ trial-skill.sh promote --group {g}{RST}"
                  f"{DIM} keeps them permanently{RST}")
            print()

    if managed:
        cost = sum(s.get("desc_chars", 0) for s in managed)
        section("MANAGED", f"{plural(len(managed), 'skill')} · ~{fmt_tokens(cost)} tokens · "
                           f"symlinks into agents-shared", BLUE)
        print()
        if args.all:
            print_cards(sorted(managed, key=lambda s: s["name"]), lambda s: BLUE)
        else:
            print_rows(sorted(managed, key=lambda s: s["name"]))

    # The bottom explainer, as in the launcher: what this state costs and the one
    # command that changes it.
    print(f"  {DIM}{'─' * min(term_width() - 4, 92)}{RST}")
    share = (trial_chars / total_chars * 100) if total_chars else 0
    print(f"  Trials are {BOLD}{share:.0f}%{RST} of your skill frontmatter "
          f"({fmt_tokens(trial_chars)} of {fmt_tokens(total_chars)} tokens).")
    if stale:
        names = ", ".join(s["name"] for s in stale[:4])
        more = f" +{len(stale) - 4} more" if len(stale) > 4 else ""
        print(f"  {RED}{len(stale)} stale{RST} "
              f"{DIM}(unused {stale_days}d+): {names}{more}{RST}")
    else:
        print(f"  {DIM}Nothing stale — stale means unused for {stale_days}d. "
              f"Pin anything you want to keep aging out.{RST}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
