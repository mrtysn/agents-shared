#!/usr/bin/env python3
# DESC: Skill Tree — a local page showing every Claude Code skill group and skill, with toggles that write the real settings
"""Thin shim: Skill Tree is now the "skills" skin of `local-repos-list serve`
(see skill_tree_skin.py next to this file, and the local-repos-list repo's
README for the skin interface). This script just execs that, passing through
the flags Skill Tree's own launcher and callers use.

Nothing here binds a port, walks a folder tree or serves a page any more —
that is all local-repos-list's job. This file keeps its name, shebang and
`# DESC:` line so `~/bin/skill-tree` and the toolbelt keep working unchanged.
"""
import argparse
import os
import shutil
import sys

SKIN_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "skill_tree_skin.py")


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve the Skill Tree page (the local-repos-list 'skills' skin).")
    ap.add_argument("--port", type=int, default=8797)
    ap.add_argument("--no-open", action="store_true", help="do not open the browser")
    ap.add_argument("--project", help="folder to select at start (anywhere under the dev root)")
    ap.add_argument("--idle-exit", type=float, metavar="MINUTES", default=0,
                     help="quit after this many minutes without a request (0 = never)")
    args = ap.parse_args()

    lrl = shutil.which("local-repos-list")
    if not lrl:
        print("local-repos-list not found on PATH; install it from the local-repos-list repo "
              "(bin/local-repos-list) and make sure ~/bin (or wherever it's linked) is on PATH.",
              file=sys.stderr)
        return 1

    cmd = [lrl, "serve", "--skin", "skills", "--port", str(args.port), "--idle-exit", str(args.idle_exit)]
    if args.no_open:
        cmd.append("--no-open")
    if args.project:
        cmd.extend(["--project", args.project])
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    sys.exit(main())
