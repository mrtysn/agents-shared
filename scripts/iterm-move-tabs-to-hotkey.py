#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["iterm2"]
# ///
"""Move every tab of every other iTerm window into the hotkey window.

The hotkey window is the one holding a tmux tab: clo attaches each Claude session with
`tmux -CC` as a tab of the window it ran in, and the owner runs clo from the hotkey
window. Exits 2 when no window or several windows hold a tmux tab, since the target is
then a guess. Needs iTerm's Python API (Settings → General → Magic → Enable Python API).
"""
import sys

import iterm2


async def main(conn):
    app = await iterm2.async_get_app(conn)
    hot = [w for w in app.terminal_windows if any(t.tmux_connection_id for t in w.tabs)]
    if len(hot) != 1:
        sys.exit(f"cannot tell which window is the hotkey window: {len(hot)} windows hold a tmux tab")
    hot = hot[0]
    moving = [t for w in app.terminal_windows if w is not hot for t in w.tabs]
    if moving:
        await hot.async_set_tabs(list(hot.tabs) + moving)
    print(f"moved {len(moving)} tab(s) into the hotkey window")


iterm2.run_until_complete(main)
