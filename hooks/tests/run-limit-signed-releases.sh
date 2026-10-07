#!/bin/bash
# DESC: Run the limit-signed-releases PreToolUse hook through its cases, each against a fresh log
#
# Each case seeds a temporary log with signings N seconds ago, feeds one command as a PreToolUse
# payload, and checks the verdict (pass = 0, block = 2) and how many signings the log holds after.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HOOK="$HERE/../limit-signed-releases.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
FAILS=0

# check <name> <expected verdict> <expected log lines after> <command> [seconds-ago...]
check() {
    local name=$1 want=$2 lines=$3 command=$4; shift 4
    local log="$WORK/log" now got after verdict
    now=$(date +%s)
    : > "$log"
    for ago in "$@"; do echo $((now - ago)) >> "$log"; done
    set +e
    jq -n --arg c "$command" '{tool_input: {command: $c}}' | SIGNED_RELEASE_LOG=$log "$HOOK" 2>/dev/null
    got=$?
    set -e
    verdict=pass; [ $got -eq 2 ] && verdict=block
    after=$(grep -c . "$log" || true)
    if [ "$verdict" = "$want" ] && [ "$after" = "$lines" ]; then
        echo "ok    $name"
    else
        echo "FAIL  $name: got $verdict with $after logged, wanted $want with $lines"
        FAILS=$((FAILS + 1))
    fi
}

SIGN='cd extension && doppler run --project firefox-signing --config prd -- npx web-ext sign --channel unlisted'
H=3600
# What counts as a signing, with an empty log: logged once.
check "the usual doppler + npx signing"            pass 1 "$SIGN"
check "web-ext sign alone"                         pass 1 'web-ext sign --channel unlisted'
check "npx --yes web-ext sign"                     pass 1 'npx --yes web-ext sign'
check "a pinned version"                           pass 1 'npx web-ext@8 sign'
check "a flag before sign"                         pass 1 'web-ext --verbose sign'
check "sign; with no space"                        pass 1 'web-ext sign; echo done'
check "yarn and pnpm dlx"                          pass 1 'yarn web-ext sign && pnpm dlx web-ext sign'
check "an env prefix"                              pass 1 'WEB_EXT_API_KEY=x web-ext sign'
check "inside bash -c"                             pass 1 'bash -c "cd extension && npx web-ext sign"'
check "inside zsh -c, single quotes"               pass 1 "zsh -c 'npx web-ext sign --channel unlisted'"
check "a repo's release.zsh"                       pass 1 'tools/release.zsh'
check "zsh running a release.zsh"                  pass 1 'zsh ./tools/release.zsh'
check "curl to AMO's upload API"                   pass 1 'curl -X POST https://addons.mozilla.org/api/v5/addons/upload/ -F upload=@x.xpi'
# What does not.
check "an unrelated command"                       pass 0 'ls -la'
check "web-ext run and lint"                       pass 0 'npx web-ext run && npx web-ext lint'
check "a quoted mention in a commit message"       pass 0 'git commit -m "ship web-ext sign batch"'
check "a grep for it"                              pass 0 'grep -r web-ext sign .'
check "curl to another AMO page"                   pass 0 'curl https://addons.mozilla.org/en-US/firefox/'
# AMO's limits: 3 a minute, 10 an hour, 24 a day.
check "a third in a minute passes"                 pass 3 "$SIGN" 10 20
check "a fourth in a minute is refused"            block 3 "$SIGN" 10 20 30
check "a tenth in an hour passes"                  pass 10 "$SIGN" 100 200 300 400 500 600 700 800 900
check "an eleventh in an hour is refused"          block 10 "$SIGN" 100 200 300 400 500 600 700 800 900 1000
check "the 24th in a day passes"                   pass 24 "$SIGN" $(for i in $(seq 1 23); do echo $((i * H - 60)); done)
check "the 25th in a day is refused"               block 24 "$SIGN" $(for i in $(seq 1 24); do echo $((i * H - 3000)); done)
check "signings older than a day do not count"     pass 4 "$SIGN" 90000 90001 90002

[ $FAILS -eq 0 ] && echo "all passed" || { echo "$FAILS FAILED"; exit 1; }
