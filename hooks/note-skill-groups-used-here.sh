#!/bin/bash
# DESC: SessionStart hook — in a repo where a globally-off skill group was used lately, notes it until the repo records a choice
#
# Optional skill groups (~/.claude/skills/<group>, the plugin <group>@skills-dir) are off in
# ~/.claude/settings.json so their descriptions stay out of every session. This hook reads the
# cache that scripts/report-skill-group-use.py --write-cache keeps (refreshed daily by the
# rule-failure-survey job) and, on a fresh start only, adds a short note naming each off group
# that was used inside this repo in the cache's window and that the repo has not decided on.
# A repo decides by listing <group>@skills-dir, true or false, under enabledPlugins in
# .claude/settings.json or .claude/settings.local.json.
#
# Silent when: the session is resumed, cleared or compacted; the folder is not in a git repo;
# the cache is missing or older than 7 days; nothing off was used here; every such group is
# decided. SKILL_GROUP_CACHE overrides the cache path (tests).
#
# Bash, not zsh, to match the hooks beside it. Written for bash 3.2 (macOS /bin/bash).

set -u

INPUT=$(cat)
SOURCE=$(printf '%s' "$INPUT" | jq -r '.source // empty')
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty')
[ "$SOURCE" = "startup" ] || exit 0
[ -n "$CWD" ] || exit 0

ROOT=$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null) || exit 0
CACHE=${SKILL_GROUP_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/skill-group-use.json}
[ -r "$CACHE" ] || exit 0

NOW=$(date +%s)
# /usr/bin/stat: the BSD stat takes -f %m; a GNU stat earlier on PATH reads -f as --file-system.
if [ -x /usr/bin/stat ] && MTIME=$(/usr/bin/stat -f %m "$CACHE" 2>/dev/null) && [ -n "${MTIME##*[!0-9]*}" ]; then :
else MTIME=$(stat -c %Y "$CACHE" 2>/dev/null) || exit 0; fi
[ -n "${MTIME##*[!0-9]*}" ] || exit 0
[ $((NOW - MTIME)) -le $((7 * 86400)) ] || exit 0

DECIDED=$(cat "$ROOT/.claude/settings.json" "$ROOT/.claude/settings.local.json" 2>/dev/null \
    | jq -s '[.[] | (.enabledPlugins // {}) | keys[]] | unique' 2>/dev/null)
[ -n "$DECIDED" ] || DECIDED='[]'

USED=$(jq -r --arg root "$ROOT" --argjson decided "$DECIDED" '
    . as $doc
    | [.groups[]
       | select(.global == false)
       | select(((.group + "@skills-dir") as $k | $decided | index($k)) | not)
       | {group, n: ([.folders | to_entries[]
                      | select(.key == $root or (.key | startswith($root + "/")))
                      | .value] | add // 0)}
       | select(.n > 0)
       | "\(.group) (\(.n) use\(if .n == 1 then "" else "s" end))"]
    | if length == 0 then empty else "\(join(", "))|\($doc.days)" end' "$CACHE" 2>/dev/null)
[ -n "$USED" ] || exit 0

LIST=${USED%|*}
DAYS=${USED##*|}
NOTE="Skill groups used in this repo in the last $DAYS days but off: $LIST. They are off globally to keep every session's skill list short, and this repo has not recorded a choice. If this session's work needs one, ask the user whether this repo should load it, and write the answer for each group listed as true or false under enabledPlugins (key <group>@skills-dir) in .claude/settings.local.json; a recorded answer stops this note. agents-shared/scripts/report-skill-group-use.py --repo . shows every group."

jq -n --arg c "$NOTE" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}'
