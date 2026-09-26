#!/bin/bash
# UserPromptSubmit hook: reads a typed prompt's kind (question, order, wish,
# correction, other) through the system-one decision model, the gate named
# 3.1 in the use-case survey and covered by question-handling.md,
# stated-desires.md and working-style.md. Also writes the outcome receipts
# for the *previous* prompt and the *previous* Stop of this session (section
# 13 of the design doc): a hook cannot know its own verdict was right until
# the next turn, so the label lands one call later, appended to the log the
# verdict itself is in.
#
# State: "prompt:\n<prompt text>", plus, when the transcript tail is readable
# cheaply, a "previous:" line with the last assistant message's first
# state.previous_chars characters (hooks/system-one-prompt-questions.json;
# 0 disables it). Questions, the act-mode context wording and the gate all
# come from that file, the single source shared with
# scripts/system-one-measure.py --hook prompt, so the hook and the harness
# build an identical request.
#
# Model: SYSTEM_ONE_PROMPT_MODEL (default english; the friendly name of a
# configured checkpoint, e.g. full-v1, to ask instead -- see scripts/system-one
# and SYSTEM_ONE_MODEL_NAME). The `kind` decision stays argmax against
# SYSTEM_ONE_PROMPT_ACT_MIN; `wants_action` is passed through --gate so its
# would_act/fired is logged and available to the status row, at the file's
# gate.wants_action threshold (val-swept per the model it names).
#
# Modes (SYSTEM_ONE_PROMPT_MODE, falling back to SYSTEM_ONE_MODE, default
# shadow):
#   shadow / show   log the verdict to shadow/prompt/<session_id>.jsonl, emit
#                   nothing, exit 0 (show is identical here; the distinct name
#                   is for status/statusline/app to say the user opted in)
#   act             when the top kind's probability is at or above
#                   SYSTEM_ONE_PROMPT_ACT_MIN (config, falls back to the
#                   questions file's act_min, default 0.60), emit
#                   hookSpecificOutput.additionalContext with exactly one
#                   line, worded per kind from the file's "context" map.
#                   order and other never get a line (empty string in that
#                   map). A slash command (prompt starts with "/") or a
#                   prompt under 3 words is never annotated, whatever the
#                   kind or probability. The line never appears in shadow or
#                   show mode.
#                   A second, independent line (section 14): the `delegate`
#                   noul question (asked in the same call as kind and
#                   wants_action -- one request, three questions) emits the
#                   file's context.delegate wording when its probability is
#                   at or above SYSTEM_ONE_PROMPT_DELEGATE_MIN (config/env,
#                   falls back to the file's delegate.min, 0.5) and the
#                   prompt has at least delegate.min_words words (8, the
#                   mining filter). Never for a slash command or a relayed
#                   message. Composition order in one additionalContext:
#                   skill line, delegate line, kind line, newline-joined.
#                   The row logs delegate_eligible (act mode, not slash, long
#                   enough) so the verdict can be read back per row.
# The outcome rows below are written in every mode, including shadow: they
# are receipts for scripts/system-one-receipts.py, not act-mode behaviour.
#   prompt-outcome  if the previous prompt of this session logged a row with
#                   an "id", append {"kind":"outcome","ref":<that id>,
#                   "next_kind":<this prompt's kind>,
#                   "next_is_command":<this prompt starts with "/">,
#                   "acted":<any assistant tool_use between the two prompts>,
#                   "tool_calls":<count>} to shadow/prompt/<session>.jsonl.
#                   "acted" is read from the transcript, bounded (tail -c)
#                   and best-effort; a read that fails just skips this row.
#   stop-outcome    for every not-yet-labelled row in
#                   shadow/stop/<session>.jsonl (the Stop hook writes one, for
#                   needless_table/overlong), append {"kind":"outcome",
#                   "ref":<that id>,"next_prompt_kind":<this prompt's kind>,
#                   "next_command":<slash command name or "">,
#                   "ran_outstanding":<next_command == "outstanding">} to
#                   shadow/stop/<session>.jsonl. Labels any row with an "id"
#                   regardless of which questions it carries, so it stays
#                   correct whether the Stop hook logged one row or several.
# Fails open on everything: no config, no wrapper, no questions file, server
# down, timeout, bad JSON, a transcript that cannot be read, a shadow log
# that cannot be read or written. Must stay under ~300 ms, so every read is
# bounded (tail -c / tail -n) and best-effort only; a receipt that cannot be
# built is simply not written, and never blocks the call.
#
# Relay skip: before any of the above, a prompt starting with or containing
# one of questions.json's skip_prefixes/skip_markers (subagent hand-back,
# cross-session message, task notification, system reminder) exits 0
# immediately -- not classified, not logged, not annotated, and not treated
# as "next prompt" for the outcome receipts, which stay pinned to the
# previous *typed* prompt until one actually arrives.
#
# Shadow log: --keep-state, so the row carries the full state the model saw
# (the prompt cut to state.prompt_chars, plus the previous: excerpt when
# enabled) -- that is what scripts/system-one-receipts.py --export-cases
# turns into training rows once the outcome row labels it. Growth: at most
# ~600 bytes more per prompt, under the state dir only, never the repo.
#
# Bash 3.2, like the hooks beside it.

set -u

INPUT=$(cat)
PROMPT=$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null)
[ -n "$PROMPT" ] || exit 0
SESSION=$(printf '%s' "$INPUT" | jq -r '.session_id // ""' 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
QUESTIONS_FILE="$HERE/system-one-prompt-questions.json"

# Deterministic relay skip: UserPromptSubmit also fires for text the harness
# itself injects between turns -- subagent hand-backs, cross-session
# messages, task notifications, system reminders. None of those are a typed
# prompt, so none of them are classified, logged, or annotated: exit before
# the wrapper is even located, no model call, no shadow-log write. A relayed
# message therefore also never labels a *previous* prompt's row (it is not
# "next prompt" for the prompt-outcome or stop-outcome receipts below) --
# those stay unlabelled until an actual typed prompt follows, which is
# correct: the receipt asks what the user did in response, and a relayed
# message is not the user responding. Markers list lives in
# system-one-prompt-questions.json (skip_prefixes/skip_markers) so it can
# grow without touching this script.
SKIP_MARKERS=$(jq -r '(.skip_prefixes // []) + (.skip_markers // []) | .[]' "$QUESTIONS_FILE" 2>/dev/null)
if [ -n "$SKIP_MARKERS" ]; then
    while IFS= read -r marker; do
        [ -n "$marker" ] || continue
        case "$PROMPT" in
            *"$marker"*) exit 0 ;;
        esac
    done <<<"$SKIP_MARKERS"
fi

WRAPPER="$HERE/../scripts/system-one"
[ -x "$WRAPPER" ] || exit 0

QUESTIONS=$(jq -c '.questions // empty' "$QUESTIONS_FILE" 2>/dev/null)
[ -n "$QUESTIONS" ] || exit 0
FILE_ACT_MIN=$(jq -r '.act_min // .threshold // 0.60' "$QUESTIONS_FILE" 2>/dev/null)
PREV_CHARS=$(jq -r '.state.previous_chars // 300' "$QUESTIONS_FILE" 2>/dev/null)
PROMPT_CHARS=$(jq -r '.state.prompt_chars // 600' "$QUESTIONS_FILE" 2>/dev/null)
CONTEXT=$(jq -c '.context // {}' "$QUESTIONS_FILE" 2>/dev/null)
GATE=$(jq -c '.gate // {}' "$QUESTIONS_FILE" 2>/dev/null)
FILE_DELEGATE_MIN=$(jq -r '.delegate.min // 0.5' "$QUESTIONS_FILE" 2>/dev/null)
DELEGATE_MIN_WORDS=$(jq -r '.delegate.min_words // 8' "$QUESTIONS_FILE" 2>/dev/null)
ALLOW_BARE=$(jq -r '.skill_name_rule.allow_bare // [] | .[]' "$QUESTIONS_FILE" 2>/dev/null | tr 'A-Z' 'a-z')
ROSTER_TTL=$(jq -r '.skill_name_rule.roster_ttl_seconds // 600' "$QUESTIONS_FILE" 2>/dev/null)
SKILL_WORD_ONE=$(jq -r '.skill_name_rule.wording_one // ""' "$QUESTIONS_FILE" 2>/dev/null)
SKILL_WORD_MANY=$(jq -r '.skill_name_rule.wording_many // ""' "$QUESTIONS_FILE" 2>/dev/null)

# Config: sourced in a subshell, only the keys this hook reads come back, so
# an exported SYSTEM_ONE_* the caller set (STATE_DIR, PORT) is never
# re-assigned here and reaches the wrapper intact: environment wins over the
# file, per key (see hooks/system-one-bash.sh for the full reasoning).
# SYSTEM_ONE_STATE_DIR is also read here (not just by the wrapper): the
# outcome receipts below read and append shadow-log files directly, the same
# fast path cc-statusline.js uses, rather than paying for a second and third
# wrapper process per prompt.
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/system-one.local.sh"
[ -r "$CONFIG" ] || exit 0
PRE_MODE="${SYSTEM_ONE_PROMPT_MODE:-${SYSTEM_ONE_MODE:-}}"
PRE_MODEL="${SYSTEM_ONE_PROMPT_MODEL:-}"
PRE_ACT_MIN="${SYSTEM_ONE_PROMPT_ACT_MIN:-}"
PRE_DELEGATE_MIN="${SYSTEM_ONE_PROMPT_DELEGATE_MIN:-}"
PRE_STATE_DIR="${SYSTEM_ONE_STATE_DIR:-}"
CFG=$( ( . "$CONFIG" 2>/dev/null || exit 1
    printf '%s\037%s\037%s\037%s\037%s\037%s' "${SYSTEM_ONE_PROMPT_MODE:-}" "${SYSTEM_ONE_MODE:-}" \
        "${SYSTEM_ONE_PROMPT_MODEL:-}" "${SYSTEM_ONE_PROMPT_ACT_MIN:-}" "${SYSTEM_ONE_PROMPT_DELEGATE_MIN:-}" \
        "${SYSTEM_ONE_STATE_DIR:-}" ) ) || exit 0
IFS=$'\037' read -r CFG_PROMPT_MODE CFG_MODE CFG_MODEL CFG_ACT_MIN CFG_DELEGATE_MIN CFG_STATE_DIR <<<"$CFG"
MODE="${PRE_MODE:-${CFG_PROMPT_MODE:-${CFG_MODE:-shadow}}}"
MODEL="${PRE_MODEL:-${CFG_MODEL:-english}}"
ACT_MIN="${PRE_ACT_MIN:-${CFG_ACT_MIN:-${FILE_ACT_MIN:-0.60}}}"
DELEGATE_MIN="${PRE_DELEGATE_MIN:-${CFG_DELEGATE_MIN:-${FILE_DELEGATE_MIN:-0.5}}}"
STATE_DIR="${PRE_STATE_DIR:-${CFG_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/system-one}}"
SHADOW_DIR="$STATE_DIR/shadow"

# Session id, safe for a filename: same rule scripts/system-one's
# session_file_id and cc-statusline.js's readVerdict already use (word
# characters and dashes only; empty becomes _nosession).
SESSION_SAFE=$(printf '%s' "$SESSION" | tr -dc 'A-Za-z0-9_-')
[ -n "$SESSION_SAFE" ] || SESSION_SAFE=_nosession
PROMPT_LOG="$SHADOW_DIR/prompt/$SESSION_SAFE.jsonl"
STOP_LOG="$SHADOW_DIR/stop/$SESSION_SAFE.jsonl"

# Capture the previous prompt-hook row's id/ts *before* this call appends a
# new one for the current prompt, so "previous" unambiguously means the row
# from the prompt before this one. Last 20 lines is enough: the prompt hook
# writes at most one verdict row plus one outcome row per prompt.
PREV_ID=""
PREV_TS=""
PREV_EPOCH=""
if [ -r "$PROMPT_LOG" ]; then
    PREV_LINE=$(tail -n 20 "$PROMPT_LOG" 2>/dev/null | jq -c 'select((.kind // "") != "outcome") | select(.id != null)' 2>/dev/null | tail -n 1)
    if [ -n "$PREV_LINE" ]; then
        PREV_ID=$(printf '%s' "$PREV_LINE" | jq -r '.id // empty' 2>/dev/null)
        PREV_TS=$(printf '%s' "$PREV_LINE" | jq -r '.ts // empty' 2>/dev/null)
        PREV_EPOCH=$(printf '%s' "$PREV_LINE" | jq -r '.ts_epoch // empty' 2>/dev/null)
    fi
fi

# Best-effort "previous:" excerpt: the last assistant text message in the
# transcript's tail. Bounded read (last 64 KiB) and a hard skip on anything
# that fails, to keep this well under the hook's latency budget.
# Lines are parsed one at a time (fromjson?) because the tail's first line is
# usually cut mid-JSON; a slurp would fail on it and lose the whole read. The
# excerpt is the message's last PREV_CHARS characters: the end of an assistant
# message (its ask or conclusion) is what the next prompt answers.
PREVIOUS=""
if [ "$PREV_CHARS" != 0 ] && [ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ]; then
    PREVIOUS=$(tail -c 65536 "$TRANSCRIPT" 2>/dev/null | jq -Rrn --argjson n "$PREV_CHARS" '
        [inputs | fromjson? | select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text]
        | last // "" | .[-$n:]' 2>/dev/null)
fi

# The prompt is capped (state.prompt_chars): the encoder's state budget is
# about 300 tokens, and a pasted wall of text would push the previous excerpt
# out entirely; the opening of a prompt carries its kind.
STATE="prompt:
${PROMPT:0:$PROMPT_CHARS}"
if [ -n "$PREVIOUS" ]; then
    STATE="$STATE
previous:
$PREVIOUS"
fi

# Slash command: everything after the leading "/" up to the first space,
# used for the "never annotated" filters, next_command below, and the
# delegate eligibility logged with the row.
SLASH_CMD=""
case "$PROMPT" in
    /*) SLASH_CMD=${PROMPT#/}; SLASH_CMD=${SLASH_CMD%% *} ;;
esac
WORDCOUNT=$(printf '%s' "$PROMPT" | wc -w | tr -d ' ')
WORDCOUNT=${WORDCOUNT:-0}
# delegate_eligible: act mode, typed (not a slash command), and at least
# delegate.min_words words -- the same anchor filter the delegate rows were
# mined with. Decided before the call so it lands in the verdict row itself;
# the probability lands there anyway as answers.delegate.noul.
DELEGATE_ELIGIBLE=false
if [ "$MODE" = act ] && [ -z "$SLASH_CMD" ] && [ "$WORDCOUNT" -ge "${DELEGATE_MIN_WORDS:-8}" ] 2>/dev/null; then
    DELEGATE_ELIGIBLE=true
fi

# No `|| exit 0` here (unlike this call elsewhere): a failed/timed-out ask
# must not kill the whole hook, because the deterministic skill-name rule
# below has no model call and has to keep working when this one fails.
# Everything downstream already tolerates an empty RESP (KIND/PROB/DELEGATE_P
# stay "", the outcome-receipt blocks guard on `-n "$KIND"` or emit null).
# One call carries all three questions (kind, wants_action, delegate).
RESP=$(jq -cn --arg s "$STATE" --argjson q "$QUESTIONS" '{state: $s, questions: $q}' 2>/dev/null \
    | "$WRAPPER" ask --hook prompt --session "$SESSION" --model "$MODEL" --gate "$GATE" --keep-state --fail-open \
        --extra "{\"delegate_eligible\":$DELEGATE_ELIGIBLE}" 2>/dev/null)

# KIND/PROB are needed for the outcome receipts below in every mode, not just
# act, so they are computed unconditionally once RESP exists.
KIND=""
PROB=""
DELEGATE_P=""
if [ -n "$RESP" ]; then
    TOP=$(printf '%s' "$RESP" | jq -r '
        (.answers.kind.probabilities // {}) | to_entries | max_by(.value) // {key: "", value: 0}
        | "\(.key) \(.value)"' 2>/dev/null)
    KIND=${TOP% *}
    PROB=${TOP#* }
    DELEGATE_P=$(printf '%s' "$RESP" | jq -r '.answers.delegate.noul // empty' 2>/dev/null)
fi

# --- prompt-outcome: label the *previous* prompt's verdict with this one ---
if [ -n "$PREV_ID" ] && [ -n "$KIND" ]; then
    IS_CMD=false
    [ -n "$SLASH_CMD" ] && IS_CMD=true
    ACTED=false
    TOOL_CALLS=0
    if [ -n "$TRANSCRIPT" ] && [ -r "$TRANSCRIPT" ] && { [ -n "$PREV_EPOCH" ] || [ -n "$PREV_TS" ]; }; then
        # The verdict row's ts_epoch is the boundary. Rows from before
        # ts_epoch existed (the first prompt after that change in a session
        # that was already running) fall back to parsing ts by hand: jq's
        # strptime("%z") silently ignores the numeric offset on this platform
        # (mktime always means timegm, never localtime; verified against
        # Python for +0300, +0200, -0700 and -0800 across DST boundaries), so
        # the fixed-width offset of scripts/system-one's own
        # "%Y-%m-%dT%H:%M:%S%z" is parsed and subtracted instead.
        SINCE="$PREV_EPOCH"
        case "$SINCE" in *[!0-9]*|"") SINCE="" ;; esac
        [ -n "$SINCE" ] || SINCE=$(jq -n --arg t "$PREV_TS" '
            ($t[0:19] + "Z") as $u
            | ($u | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime) as $naive
            | ($t[19:20]) as $sign
            | (($t[20:22] | tonumber) * 3600 + ($t[22:24] | tonumber) * 60) as $mag
            | (if $sign == "-" then -$mag else $mag end) as $off
            | $naive - $off' 2>/dev/null)
        if [ -n "$SINCE" ]; then
            TOOL_CALLS=$(tail -c 262144 "$TRANSCRIPT" 2>/dev/null | jq -Rrn --argjson since "$SINCE" '
                [inputs | fromjson?
                 | select(.type == "assistant" and (.timestamp // null) != null)
                 | select((.timestamp | sub("\\.[0-9]+Z$"; "Z") | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime) > $since)
                 | .message.content[]? | select(.type == "tool_use")] | length' 2>/dev/null)
            [ -n "$TOOL_CALLS" ] || TOOL_CALLS=0
        fi
    fi
    [ "$TOOL_CALLS" -gt 0 ] 2>/dev/null && ACTED=true
    mkdir -p "$(dirname "$PROMPT_LOG")" 2>/dev/null
    # One appended line per row (jq -c, >>): no read-modify-write, so a
    # concurrent writer to the same file (the Stop hook, bash-post) can only
    # interleave whole lines. Same for every append below.
    jq -cn --arg ref "$PREV_ID" --arg k "$KIND" --argjson cmd "$IS_CMD" --argjson acted "$ACTED" --argjson n "$TOOL_CALLS" \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" \
        '{ts: $ts, kind: "outcome", ref: $ref, next_kind: $k, next_is_command: $cmd, acted: $acted, tool_calls: $n}' \
        >>"$PROMPT_LOG" 2>/dev/null
fi

# --- stop-outcome: label every not-yet-labelled Stop row of this session ---
if [ -r "$STOP_LOG" ]; then
    NEXT_CMD="$SLASH_CMD"
    RAN_OUT=false
    [ "$NEXT_CMD" = outstanding ] && RAN_OUT=true
    STOP_TAIL=$(tail -n 20 "$STOP_LOG" 2>/dev/null)
    if [ -n "$STOP_TAIL" ]; then
        ALREADY=$(printf '%s\n' "$STOP_TAIL" | jq -r 'select((.kind // "") == "outcome") | .ref // empty' 2>/dev/null)
        UNLABELLED=$(printf '%s\n' "$STOP_TAIL" | jq -r 'select((.kind // "") != "outcome") | select(.id != null) | .id' 2>/dev/null)
        if [ -n "$UNLABELLED" ]; then
            # next_prompt_kind is null, not "", when this prompt's own
            # classification failed (server down or slow): the other two
            # fields do not depend on the model and stay valid.
            while IFS= read -r rid; do
                [ -n "$rid" ] || continue
                printf '%s\n' "$ALREADY" | grep -qxF "$rid" && continue
                jq -cn --arg ref "$rid" --arg k "$KIND" --arg cmd "$NEXT_CMD" --argjson out "$RAN_OUT" \
                    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" \
                    '{ts: $ts, kind: "outcome", ref: $ref, next_prompt_kind: (if $k == "" then null else $k end), next_command: $cmd, ran_outstanding: $out}' \
                    >>"$STOP_LOG" 2>/dev/null
            done <<<"$UNLABELLED"
        fi
    fi
fi

# --- act mode: additionalContext, gated and filtered ---
# Two independent lines can fire here, skill-name first: the deterministic
# skill-routing rule below (no model call, so it still works when the server
# or model call above failed and KIND is empty) and the model's kind line
# (needs KIND/PROB, computed above). Neither depends on the other; either,
# both, or neither may appear, joined by a newline in one additionalContext.
[ "$MODE" = act ] || exit 0
[ -z "$SLASH_CMD" ] || exit 0
[ "$WORDCOUNT" -ge 3 ] 2>/dev/null || exit 0

# --- deterministic skill-name rule (section: skill routing) ---
# Fires when the prompt explicitly names a roster skill or slash command:
# "/<name>" anywhere, or the bare name when it is hyphenated/multi-token
# (stg-msg-cmt, search-history, new-repo, be-literal, ...) or listed in
# questions.json's skill_name_rule.allow_bare (single-word names that would
# otherwise collide with ordinary English -- humanizer, archify, ...). No
# model call. Roster: a literal ls of $CLAUDE_CONFIG_DIR/skills/*/SKILL.md
# and .../commands/*.md (top-level only -- a plugin group directory like
# interface/ or motion/ has no SKILL.md of its own, so its sub-skills
# (better-ui, animate, ...) are not in scope for this rule), cached to
# STATE_DIR for skill_name_rule.roster_ttl_seconds (default 600s) so a cold
# ls (~5-10ms; ~150 dirs) is paid at most once per that window and every
# other call reads one small file. Measured 2026-09-26: cold roster build
# ~5ms (pure bash parameter expansion, no forked basename/dirname), cached
# read <1ms, the awk matcher itself ~4ms -- comfortably inside the hook's
# ~300ms budget. Everything here fails open and silent: any missing dir,
# unreadable cache, or awk error just yields no skill line.
SKILL_LINE=""
ROSTER_HOME="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ROSTER_CACHE="$STATE_DIR/skill-roster.cache"
NOW_EPOCH=$(date +%s 2>/dev/null)
ROSTER=""
if [ -n "$NOW_EPOCH" ] && [ -r "$ROSTER_CACHE" ]; then
    # date -r <file> +%s (not stat -f/-c): BSD date and GNU date both accept
    # a file for -r and agree on +%s, unlike stat's -f/-c split, which on a
    # machine with GNU coreutils' stat ahead of BSD stat in PATH (gnubin)
    # silently writes a filesystem-info block to stdout before failing --
    # polluting a naive stat -f/-c fallback chain's captured output.
    CACHE_MTIME=$(date -r "$ROSTER_CACHE" +%s 2>/dev/null)
    if [ -n "$CACHE_MTIME" ] && [ $((NOW_EPOCH - CACHE_MTIME)) -lt "${ROSTER_TTL:-600}" ] 2>/dev/null; then
        ROSTER=$(cat "$ROSTER_CACHE" 2>/dev/null)
    fi
fi
if [ -z "$ROSTER" ]; then
    RNAMES=""
    for f in "$ROSTER_HOME"/skills/*/SKILL.md; do
        [ -e "$f" ] || continue
        d="${f%/SKILL.md}"
        RNAMES="$RNAMES${d##*/}
"
    done
    for f in "$ROSTER_HOME"/commands/*.md; do
        [ -e "$f" ] || continue
        b="${f##*/}"
        RNAMES="$RNAMES${b%.md}
"
    done
    ROSTER=$(printf '%s' "$RNAMES" | tr 'A-Z' 'a-z' | sort -u 2>/dev/null)
    if [ -n "$ROSTER" ]; then
        mkdir -p "$STATE_DIR" 2>/dev/null
        printf '%s\n' "$ROSTER" >"$ROSTER_CACHE.tmp.$$" 2>/dev/null \
            && mv "$ROSTER_CACHE.tmp.$$" "$ROSTER_CACHE" 2>/dev/null
    fi
fi
if [ -n "$ROSTER" ]; then
    ALLOW_JOINED=$(printf '%s\n' "$ALLOW_BARE" | tr '\n' '\037')
    # Newlines flattened to spaces before -v: this platform's awk (the BWK
    # "one true awk") errors on a raw newline inside a -v value, and the
    # matcher only ever splits the prompt on whitespace anyway, so a space is
    # equivalent input for its purposes.
    PROMPT_FLAT=$(printf '%s' "$PROMPT" | tr '\n\t' '  ')
    MATCHED=$(printf '%s\n' "$ROSTER" | awk -v prompt="$PROMPT_FLAT" -v allow="$ALLOW_JOINED" '
        BEGIN {
            lp = tolower(prompt)
            n = split(lp, toks, /[ \t]+/)
            nallow = split(allow, allowarr, "\037")
            for (i = 1; i <= nallow; i++) if (allowarr[i] != "") allowset[allowarr[i]] = 1
        }
        { name = tolower($0); if (name != "") roster[name] = 1 }
        END {
            for (i = 1; i <= n; i++) {
                tok = toks[i]
                gsub(/^["\x27(\[{<.,!?:;*`]+|["\x27)\]}>.,!?:;*`]+$/, "", tok)
                if (tok == "") continue
                # Terminal-paste guard: a name immediately followed by a CLI
                # flag token ("search-history --resume") is pasted shell
                # output, not a request to invoke the skill.
                nextraw = (i < n) ? toks[i + 1] : ""
                if (index(nextraw, "--") == 1) continue
                name = tok
                is_slash = 0
                if (substr(tok, 1, 1) == "/") { name = substr(tok, 2); is_slash = 1 }
                if (!(name in roster)) continue
                if (is_slash) { matched[name] = 1; continue }
                if (index(name, "-") > 0 || (name in allowset)) matched[name] = 1
            }
            out = ""
            for (m in matched) out = out (out == "" ? "" : "\n") m
            print out
        }' 2>/dev/null)
    if [ -n "$MATCHED" ]; then
        LIST=""
        NCOUNT=0
        while IFS= read -r nm; do
            [ -n "$nm" ] || continue
            NCOUNT=$((NCOUNT + 1))
            LIST="${LIST:+$LIST, }/$nm"
        done <<<"$MATCHED"
        if [ "$NCOUNT" -eq 1 ] 2>/dev/null; then
            [ -n "$SKILL_WORD_ONE" ] && SKILL_LINE=$(printf "$SKILL_WORD_ONE" "$LIST" 2>/dev/null)
        elif [ "$NCOUNT" -gt 1 ] 2>/dev/null; then
            [ -n "$SKILL_WORD_MANY" ] && SKILL_LINE=$(printf "$SKILL_WORD_MANY" "$LIST" 2>/dev/null)
        fi
    fi
fi

# --- delegate line (section 14): its own gate, its own word floor ---
DELEGATE_LINE=""
if [ "$DELEGATE_ELIGIBLE" = true ] && [ -n "$DELEGATE_P" ] \
    && awk -v p="$DELEGATE_P" -v t="$DELEGATE_MIN" 'BEGIN { exit !(p+0 >= t+0) }' 2>/dev/null; then
    DELEGATE_LINE=$(printf '%s' "$CONTEXT" | jq -r --argjson p "$DELEGATE_P" '
        (.delegate // "") as $tmpl
        | if $tmpl == "" then "" else ($tmpl | sub("%\\.2f"; ($p * 100 | round / 100 | tostring))) end' 2>/dev/null)
fi

# --- model kind line (unchanged behaviour, just no longer exits early) ---
KIND_LINE=""
if [ -n "$KIND" ] && awk -v p="$PROB" -v t="$ACT_MIN" 'BEGIN { exit !(p+0 >= t+0) }' 2>/dev/null; then
    KIND_LINE=$(printf '%s' "$CONTEXT" | jq -r --arg k "$KIND" --argjson p "$PROB" '
        (.[$k] // "") as $tmpl
        | if $tmpl == "" then "" else ($tmpl | sub("%\\.2f"; ($p * 100 | round / 100 | tostring))) end' 2>/dev/null)
fi

# Compose: skill, delegate, kind -- each optional, newline-joined into one
# additionalContext string.
OUT=""
for line in "$SKILL_LINE" "$DELEGATE_LINE" "$KIND_LINE"; do
    [ -n "$line" ] || continue
    if [ -n "$OUT" ]; then
        OUT="$OUT
$line"
    else
        OUT="$line"
    fi
done
[ -n "$OUT" ] || exit 0
jq -cn --arg c "$OUT" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
exit 0
