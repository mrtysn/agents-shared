#!/bin/bash
# DESC: Run the note-skill-groups-used-here SessionStart hook against a fake repo and cache

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../note-skill-groups-used-here.sh"
TMP=$(mktemp -d)
trap '[ -n "${TMP:-}" ] && rm -rf "$TMP"' EXIT

REPO="$TMP/repo"
mkdir -p "$REPO/sub"
git -C "$REPO" init -q
REPO=$(git -C "$REPO" rev-parse --show-toplevel)
export SKILL_GROUP_CACHE="$TMP/cache.json"
export SKILL_GROUP_LOG="$TMP/no-log.tsv"   # never the real switch log
jq -n --arg r "$REPO" '{days: 30, groups: [
    {group: "motion", global: false, folders: {($r): 2}},
    {group: "tooling", global: false, folders: {($r + "/sub"): 1}},
    {group: "threejs", global: false, folders: {"/elsewhere": 4}},
    {group: "interface", global: true, folders: {($r): 9}}]}' > "$SKILL_GROUP_CACHE"

total=0
failed=0
check() {  # name, source, cwd, expected substring or "" for silence
    total=$((total + 1))
    out=$(jq -n --arg s "$2" --arg c "$3" '{source: $s, cwd: $c}' | "$HOOK")
    if [ -z "$4" ]; then
        [ -z "$out" ] && return
    else
        printf '%s' "$out" | jq -r '.hookSpecificOutput.additionalContext' | grep -qF -- "$4" && return
    fi
    failed=$((failed + 1))
    echo "FAIL  $1: got '$out'"
}

check "fresh start names used off groups" startup "$REPO" "motion (2 uses), tooling (1 use)"
check "subfolder session counts for its repo" startup "$REPO/sub" "motion (2 uses)"
check "groups used elsewhere and groups on are left out" startup "$REPO" "tooling (1 use). They are off"
check "the note has the agent switch a group on itself" startup "$REPO" "switch it on yourself: agents-shared/scripts/enable-skill-group.zsh <group>"
check "resume is silent" resume "$REPO" ""
check "outside a git repo is silent" startup "$TMP" ""

mkdir -p "$REPO/.claude"
echo '{"enabledPlugins": {"motion@skills-dir": false}}' > "$REPO/.claude/settings.local.json"
check "a decided group drops out" startup "$REPO" "off: tooling (1 use)."
echo '{"enabledPlugins": {"motion@skills-dir": false, "tooling@skills-dir": true}}' > "$REPO/.claude/settings.local.json"
check "every group decided is silent" startup "$REPO" ""

# An agent switched react and art on here (react long ago, art recently) and threejs long ago then off.
export SKILL_GROUP_LOG="$TMP/switches.tsv"
printf '%s\t%s\t%s\t%s\t%s\n' \
    2020-01-01T00:00:00 "$REPO" react on "needed once" \
    2099-01-01T00:00:00 "$REPO" art on "needed now" \
    2020-01-01T00:00:00 "$REPO" threejs on "x" \
    2020-01-02T00:00:00 "$REPO" threejs off "done" > "$SKILL_GROUP_LOG"
echo '{"enabledPlugins": {"motion@skills-dir": false, "tooling@skills-dir": true, "react@skills-dir": true, "art@skills-dir": true}}' > "$REPO/.claude/settings.local.json"
check "a group switched on long ago and unused is named for switching off" startup "$REPO" "unused since: react. Unless"
echo '{"enabledPlugins": {"motion@skills-dir": false, "tooling@skills-dir": true, "react@skills-dir": false}}' > "$REPO/.claude/settings.local.json"
check "a stale group already off again is silent" startup "$REPO" ""
export SKILL_GROUP_LOG="$TMP/no-log.tsv"

rm "$REPO/.claude/settings.local.json"
touch -t 202001010000 "$SKILL_GROUP_CACHE"
check "a stale cache is silent" startup "$REPO" ""

printf '\n%s cases, %s failed\n' "$total" "$failed"
[ "$failed" = "0" ]
