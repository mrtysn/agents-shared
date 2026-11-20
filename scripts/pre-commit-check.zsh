#!/bin/zsh
# DESC: agents-shared's pre-commit: refuse staged conflict markers, and run check-skills.zsh when skills, rules or groups change
#
# Installed by scripts/init-global.sh as this repo's own .git/hooks/pre-commit, which the
# githooks/pre-commit dispatcher runs. Skills are served live from the working tree, so a commit is
# the gate before other machines pull them:
#   - a staged text file holding both a `<<<<<<< ` and a `>>>>>>> ` line (an unresolved merge,
#     such as a sync conflict) is refused;
#   - a commit touching claude/, scripts/check-skills.zsh or claude/skill-groups.json runs
#     scripts/check-skills.zsh, and its problems refuse the commit.
# Bypass for one commit only when the user says so: git commit --no-verify.
set -uo pipefail

root=$(git rev-parse --show-toplevel) || exit 0
staged=(${(f)"$(git diff --cached --name-only --diff-filter=ACMR)"})
(( ${#staged} )) || exit 0

conflicted=()
for f in $staged; do
  if git show ":$f" 2>/dev/null | LC_ALL=C grep -qIE '^<<<<<<< ' &&
     git show ":$f" 2>/dev/null | LC_ALL=C grep -qIE '^>>>>>>> '; then
    conflicted+=$f
  fi
done
if (( ${#conflicted} )); then
  print -u2 "pre-commit: unresolved conflict markers in: ${(j:, :)conflicted}"
  print -u2 "  Resolve them (keep the <!-- LOCAL --> intent; claude/skills/update-external-skills/SKILL.md step 4), then commit."
  exit 1
fi

if (( ${staged[(I)claude/*]} || ${staged[(I)scripts/check-skills.zsh]} )); then
  if ! out=$(zsh $root/scripts/check-skills.zsh 2>&1); then
    print -u2 -r -- "$out" | grep -E '^!!' >&2
    print -u2 "pre-commit: scripts/check-skills.zsh found problems (above); fix them, or run scripts/init-global.sh if a skill is not linked yet."
    exit 1
  fi
fi
exit 0
