# In zsh, `log` is a builtin: call `/usr/bin/log`

**The agent's shell is zsh, and zsh has a `log` builtin (it lists logins), so `log show …` never
runs macOS's unified-log tool.** It fails with `log:1: too many arguments`; with `2>/dev/null` or a
`| grep` after it, the failure is silent and the query looks like it found nothing.

Write `/usr/bin/log show …` (or `command log show …`). An empty result from a bare `log show` is
not evidence that nothing was logged; rerun it with the full path before concluding anything.

## Provenance

Nov 27 2026, notebook: diagnosing Spotlight, `log show --predicate 'process == "Siri AI"' 2>/dev/null`
returned 0 lines; `/usr/bin/log` returned 17,000 for the same window. A Nov 23 session had concluded
"the system log holds nothing from Siri AI before the restart", which may have been the same trap.
