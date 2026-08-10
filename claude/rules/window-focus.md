# Window focus

**Never open a window that steals keyboard focus unless this machine allows it.**
Some machines are shared with real work on the same screen; a game engine, a
browser, or a simulator grabbing focus mid-sentence is a genuine interruption,
and it is worse when it happens five times in a row during an iteration loop.

The verdict is per-machine, not per-task, and is injected into every session by
the `SessionStart` hook `agents-shared/hooks/focus-policy.sh` — look for a
`Focus policy: ALLOW` / `Focus policy: DENY` line. Check it yourself at any time
with `agents-shared/hooks/focus-policy.sh --verdict`, or gate a script on
`--check` (exit 0 = allowed). Unknown machines are DENY: the only allow-list is
`focus-allow` in the Claude config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`),
one hostname or glob per line. A missing or empty file denies everywhere.

Under DENY:

- **Reach for the headless mode first.** Almost everything an agent runs has
  one, and almost nothing an agent needs actually requires pixels: parse checks,
  test suites, and any probe whose answer is *printed* all run windowless. Godot:
  `--headless`. Print the state instead of looking at it.
- **If the task genuinely needs rendered pixels** — a frame capture, a screenshot
  diff, a shader that only exists on the GPU — say so and ask before running it.
- **Then batch it.** One run that captures everything, not one run per question.
  Iterating a windowed command is the behaviour that actually costs the user
  their attention, far more than any single launch.
- **Keep the window off the working display** with the tool's own flags. Godot
  has `--screen <N>` and `--position <X>,<Y>`; `--resolution` keeps it small.
- **Never re-run a windowed command "just to check."**
