# Shell scripts — prefer zsh

**zsh is the shell here.** New scripts get `#!/bin/zsh` and may use zsh features
freely: glob qualifiers (`*(N/)`), `${var:t}` / `${var:h}` modifiers, `${arr:#pattern}`
filtering, `read "VAR?prompt"`, real arrays without `declare -a`.

**Run a script with the interpreter in its shebang.** Never `bash some-script.sh`
when the file says `#!/bin/zsh` — zsh-only syntax dies with a bare
`syntax error near unexpected token` that looks like a bug in the script rather
than in how it was invoked. Execute it directly (`./script.sh`, or `zsh script.sh`)
and check the shebang first when a shell script fails to parse.

## When bash or sh is correct instead

- The script runs in CI, a container, or on Linux, where `/bin/zsh` may be absent
- It is a git hook, or anything another tool invokes with a fixed interpreter
- It must be POSIX `sh` for portability

Say which one applies rather than defaulting to bash out of habit.

## Either way

- `set -euo pipefail` at the top of anything non-trivial
- Quote expansions; `"$var"`, not `$var`
- A list of background pids is an array: `pids=(); … & pids+=($!); kill $pids`, or `kill $(jobs -p)`.
  zsh does not word-split an unquoted string, so `pids="$pids $!"` then `kill $pids` passes the
  whole string as one bad argument and kills nothing. On 2026-10-20 a load test left 12 busy loops
  on every core for three hours that way: `kill $pids 2>/dev/null; echo killed` hid the failure and
  reported success. A cleanup step never sends its errors to /dev/null, and says "stopped" only after
  checking the pids are gone.

## Long commands go in a file, not the chat

**The enemy is line length, not heredocs.** Claude Code soft-wraps long lines in
rendered code blocks; on copy, every wrap point becomes a real newline plus gutter
indentation. That breaks a heredoc — the terminator is no longer at column 0 — and
breaks a single-line base64 blob just as thoroughly. "Make it one line" does not
fix it.

Write anything longer than roughly one terminal line to a file yourself, then hand
over a short runner: `zsh /tmp/thing.sh`. Paste raw commands only when they are
short enough never to wrap.
