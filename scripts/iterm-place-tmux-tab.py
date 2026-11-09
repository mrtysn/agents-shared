#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = ["iterm2"]
# ///
"""Move the tab iTerm opens for a `tmux -CC` attach into the launching tab's place.

iTerm always appends tmux tabs at the end of the window. clo starts this in the
background just before it execs `tmux -CC`, passing the launching session's id and
its tab index (both from ITERM_SESSION_ID, "w0t3p0:<uuid>"). It waits for the tmux
connection owned by that session to show a tab, waits for the launching tab to be
buried, then moves the tmux tab to the index the launching tab had.

Needs iTerm's Python API (Settings → General → Magic → Enable Python API). Gives up
quietly after --timeout seconds; a tab left at the end is the only cost.
"""
import argparse
import asyncio
import sys

import iterm2


async def place(conn, gateway: str, index: int, timeout: float) -> str:
    app = await iterm2.async_get_app(conn)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        await app.async_refresh()
        owned = [c.connection_id for c in await iterm2.async_get_tmux_connections(conn)
                 if c.owning_session and c.owning_session.session_id == gateway]
        for window in app.terminal_windows:
            new = [t for t in window.tabs if owned and t.tmux_connection_id in owned]
            gateway_shown = any(s.session_id == gateway for t in window.tabs for s in t.sessions)
            if new and not gateway_shown:
                rest = [t for t in window.tabs if t not in new]
                at = min(index, len(rest))
                order = rest[:at] + new + rest[at:]
                if order != window.tabs:
                    await window.async_set_tabs(order)
                return f"moved {len(new)} tab(s) to index {at}"
        await asyncio.sleep(0.25)
    return "gave up: no tmux tab appeared with the launching tab buried"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gateway", required=True, help="the launching iTerm session's uuid")
    ap.add_argument("--index", required=True, type=int, help="the launching tab's 0-based index")
    ap.add_argument("--timeout", type=float, default=20.0)
    a = ap.parse_args()
    result = []

    async def run(conn):
        result.append(await place(conn, a.gateway, a.index, a.timeout))

    iterm2.run_until_complete(run)
    print(f"iterm-place-tmux-tab: {result[0] if result else 'no result'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
