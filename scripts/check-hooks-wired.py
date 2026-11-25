#!/usr/bin/env python3
"""Check that every hook the README documents is wired in a Claude settings.json, and back.

Hooks here run only once a settings.json names them, and that file is kept elsewhere
(the owner's dev-env builds it from a base file plus profile overlays). A pull that brings
a new hook therefore changes nothing until someone adds its entry, and nothing said so:
record-clo-session.zsh sat unwired after the pull that added it (Nov 2026).

The README's hooks table is the record of which events each hook belongs to:

    | `hooks/<name>` | <events, e.g. "SessionStart, SessionEnd" or "PreToolUse (`Bash`)"> | ... |

For each documented (hook, event) pair, a settings entry under that event must name the
script, as `$AGENTS_SHARED_DIR/hooks/<name>`, `$AGENTS_SHARED/hooks/<name>` or
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/<name>` (init-global.sh links hooks there). A row
whose events name no hook event ("any", for a probe) is not checked. A row marked "personal
profile only" is checked only when the config folder's profile is personal.

In the other direction, a settings entry that names `$AGENTS_SHARED_DIR/hooks/<name>` or
`$AGENTS_SHARED/hooks/<name>` for a script this checkout does not have is reported too.

usage: check-hooks-wired.py [--settings FILE] [--readme FILE] [--hooks-dir DIR] [--profile P]
Exit 0 when everything matches, 1 with one line per gap, 2 on a usage or read error.
"""
import argparse
import json
import os
import re
import subprocess
import sys

EVENTS = (
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Stop",
    "SubagentStart", "SubagentStop", "SessionStart", "SessionEnd", "Notification",
    "PreCompact", "PermissionRequest",
)
ROW = re.compile(r"^\|\s*`hooks/([^`/]+)`([^|]*)\|([^|]*(?:\\\|[^|]*)*)\|")
EVENT_WORD = re.compile(r"\b(" + "|".join(EVENTS) + r")\b")
OWN_REF = re.compile(r"\$\{?AGENTS_SHARED(?:_DIR)?(?::-[^}]*)?\}?/hooks/([A-Za-z0-9._-]+)")
LINK_REF = re.compile(r"\.claude\}?/hooks/([A-Za-z0-9._-]+)")

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def documented(readme):
    """{hook name: (set of events, personal-only)} from the README's hooks table."""
    out = {}
    for line in readme.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        name, note, events = m.group(1), m.group(2), m.group(3)
        found = set(EVENT_WORD.findall(events))
        if found:
            out[name] = (found, "personal profile only" in note)
    return out


def wired(settings):
    """{event: set of hook names} and the list of (event, name) that point into this repo."""
    by_event, own = {}, []
    for event, groups in (settings.get("hooks") or {}).items():
        for group in groups or []:
            for hook in group.get("hooks") or []:
                cmd = hook.get("command") or ""
                names = set(OWN_REF.findall(cmd)) | set(LINK_REF.findall(cmd))
                by_event.setdefault(event, set()).update(names)
                own += [(event, n) for n in OWN_REF.findall(cmd)]
    return by_event, own


def profile_of(settings_path):
    tool = os.path.join(REPO, "scripts", "agent-profile")
    try:
        return subprocess.run([tool, os.path.dirname(os.path.abspath(settings_path))],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main():
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--settings", default=os.path.join(config, "settings.json"))
    ap.add_argument("--readme", default=os.path.join(REPO, "README.md"))
    ap.add_argument("--hooks-dir", default=os.path.join(REPO, "hooks"))
    ap.add_argument("--profile", help="personal or work; default: the settings folder's own")
    a = ap.parse_args()

    try:
        with open(a.readme) as f:
            docs = documented(f.read())
        with open(a.settings) as f:
            settings = json.load(f)
    except (OSError, ValueError) as e:
        print(f"check-hooks-wired: {e}", file=sys.stderr)
        return 2
    profile = a.profile if a.profile is not None else profile_of(a.settings)
    by_event, own = wired(settings)

    gaps = []
    for name, (events, personal_only) in sorted(docs.items()):
        if personal_only and profile != "personal":
            continue
        for event in sorted(events):
            if name not in by_event.get(event, set()):
                gaps.append(f"not wired: hooks/{name} under {event} (the README documents it there)")
    for event, name in sorted(set(own)):
        if not os.path.exists(os.path.join(a.hooks_dir, name)):
            gaps.append(f"missing script: {event} runs hooks/{name}, which this checkout does not have")

    for g in gaps:
        print(g)
    if gaps:
        print(f"Settings checked: {a.settings}. A hook entry belongs in the file that settings.json is "
              "built from (dev-env's agents/claude/settings.json, or a profile overlay), then "
              "rebuilt into the live file; an edit to the live file alone is lost at the next build.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
