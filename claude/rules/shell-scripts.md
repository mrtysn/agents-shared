# Shell scripts — prefer zsh

**New scripts get `#!/bin/zsh`, and a script runs with the interpreter in its
shebang**, never `bash some-script.sh` on a zsh file. Anything longer than about one
terminal line handed to the user goes in a file with a short runner, not pasted raw.

The full rule appears the first time a session writes or runs a shell script.
