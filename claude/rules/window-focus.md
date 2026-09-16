# Window focus

**Never open a window that becomes the active app unless it went through
`quiet-open`, or the user said yes to that batch.** Some machines are shared with
real work on the same screen; a game engine, a browser, or a simulator grabbing
focus mid-sentence is a genuine interruption, and it is worse when it happens
five times in a row during an iteration loop. A hotkey terminal makes it worse
still: it hides the instant *any* other app activates, even for a tenth of a
second.

## The verdict is a tolerance, not a licence

The `SessionStart` hook `agents-shared/hooks/focus-policy.sh` injects a
`Focus policy: ALLOW` / `Focus policy: DENY` line. Check it yourself with
`focus-policy.sh --verdict`, or gate a script on `--check` (exit 0 = allowed).
Unknown machines are DENY: the only allow-list is `focus-allow` in the Claude
config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`), one hostname or glob per
line; a missing or empty file denies everywhere.

ALLOW says the *interruption* is tolerated on that machine. It does not say a
window is harmless. It was ALLOW on the owner's machine on 2026-09-16 while
thirty windowed launches each closed the hotkey terminal. So the verdict decides
how loud to be about the exception, never whether a window may activate.

## Under either verdict: `quiet-open` first

A windowed launch of a program goes through `quiet-open <App.app> [args…]`
(the owner's `tools` repo, symlinked into `~/bin`; the hook line says whether it
is installed). It launches through `open -g` with an AppKit shim injected into
an ad-hoc re-signed copy of the app, so the app never becomes active. Read the
result, not the feeling:

- Exit 0 with `quiet: loaded` in the output — focus was untouched. No ask
  needed, and a batch of such launches needs none either.
- Exit 2 — the shim did not load and that window took focus. Stop; do not
  retry in a loop.

Only an app `quiet-open` cannot quiet — one that needs entitlements an ad-hoc
re-sign cannot carry (keychain, sandbox, camera) — becomes an ask: **one
AskUserQuestion per batch, stating the process count**, before the first
launch. A subagent never launches an activating window without that ask.

## Why both halves are required

Two different things bring a launched app to the front, and each half of
`quiet-open` stops one:

- `open -g` stops LaunchServices activating a terminal-launched app at its first
  window.
- The shim stops the app activating itself: it forces the activation policy to
  Prohibited and no-ops `activateIgnoringOtherApps:` / `activate`.

Measured on macOS with Godot 4.6.1 (2026-09-16), sampling the frontmost app and
the iTerm2 window count every 100 ms: `open -g` alone, a no-focus window flag,
`LSBackgroundOnly` in the plist, and the shim on a direct launch each still
activated the app for at least one sample and dropped the terminal's window
count to zero. Both halves together did not, across a whole run, and the
rendered frame was byte-identical to a direct launch. Off-screen `--position`
and a tiny `--resolution` change nothing about activation; they are not stealth.

## What remains under DENY

For the launches `quiet-open` cannot cover, and for everything before reaching
for a window at all:

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
