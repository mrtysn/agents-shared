# Shell scripts — prefer zsh

**New scripts get `#!/bin/zsh`, and a script runs with the interpreter in its
shebang**, never `bash some-script.sh` on a zsh file. Anything longer than about one
terminal line handed to the user goes in a file with a short runner, not pasted raw.

**A list of pids in zsh is an array** (`pids+=($!)`, `kill $pids`) or `kill $(jobs -p)`: zsh does not
split a string, so `kill $pids` on `pids=" 1 2"` kills nothing. A cleanup step never hides its errors.

The full rule appears the first time a session writes or runs a shell script.
