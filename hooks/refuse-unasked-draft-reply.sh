#!/bin/zsh
# Stop hook: refuse, once, a reply that drafts a message for the user to send in answer to a message they just
# pasted, when nothing was asked of the user since then.
#
# The failure this prevents: the user pasted a message asking whether a meeting time worked, and the agent replied
# with a ready-to-send "that time works for me", answering for the user in words they do not use. Rules on not
# acting for the user were loaded at the time.
#
# It fires when all of these hold:
#   - stop_hook_active is false (the session is not already continuing because of a Stop hook),
#   - the user's last typed prompt carries a pasted image or a <pasted_content> block (an inbound message),
#   - no AskUserQuestion call was made after that prompt,
#   - the last assistant text holds a fenced block shaped like a message: its first line a greeting ending in a
#     comma or ! (Hi, Hello, Hey, Dear, Merhaba, Selam…) and a later line a sign-off (Best, Regards, Thanks, Cheers,
#     Teşekkürler, Saygılarımla…).
# Then it blocks with {"decision":"block"} and the check to make. The continuation passes (stop_hook_active),
# so it refuses at most once per turn. Any read failure lets the stop through. No network, no model call.
#
# Covers claude/rules/drafting-messages-for-the-user.md. Cases: hooks/tests/run-refuse-unasked-draft-reply.sh.

HERE=${0:A:h}
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[[ $(print -rn -- "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) == true ]] && exit 0
TRANSCRIPT=$(print -rn -- "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[[ -r $TRANSCRIPT && -r $READER ]] || exit 0

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,agents --json --max-chars 0 2>/dev/null) || exit 0

# One jq pass: from the last typed prompt on, was a question asked, and what is the last assistant text?
VERDICT=$(print -r -- "$ROWS" | jq -rs '
  [ .[] | select(.sidechain | not) ] as $rows
  | ([ range(0; $rows | length) as $i | $rows[$i]
       | select(.group == "user" and .origin == "human" and (.meta | not)) | $i ] | max // -1) as $p
  | if $p < 0 then "pass" else
      ($rows[$p].text // "") as $prompt
      | ($p + 1) as $from
      | if ($prompt | test("\\[Image #[0-9]+\\]|<pasted_content") | not) then "pass"
        elif ([ $rows[$from:][] | select(.label == "ASK") ] | length > 0) then "pass"
        else ([ $rows[$from:][] | select(.group == "assistant") | .text ] | last // "") end
    end' 2>/dev/null) || exit 0
[[ -n $VERDICT && $VERDICT != pass ]] || exit 0

# A fenced block whose first non-empty line is a greeting ending in a comma or !, and a later line a sign-off.
GREETING='^(hi|hello|hey|dear|merhaba|selam|selamlar|good (morning|afternoon|evening))\b|^[[:alpha:]çğıöşüİ]+ (selamlar|merhaba)\b'
SIGNOFF='^(best|best regards|kind regards|warm regards|regards|thanks|thank you|many thanks|cheers|sincerely|teşekkürler|teşekkür ederim|saygılarımla|sevgiler|iyi çalışmalar)\b'
found=0
inblock=0
first=""
signed=0
for line in "${(@f)VERDICT}"; do
  if [[ $line == '```'* ]]; then
    if (( inblock )); then
      if [[ $first == *[,!] ]] && print -r -- "$first" | grep -qiE "$GREETING" && (( signed )); then found=1; break; fi
      inblock=0
    else
      inblock=1; first=""; signed=0
    fi
    continue
  fi
  (( inblock )) || continue
  trimmed=${line##[[:space:]]#}
  [[ -z $trimmed ]] && continue
  if [[ -z $first ]]; then first=$trimmed; continue; fi
  print -r -- "$trimmed" | grep -qiE "$SIGNOFF" && signed=1
done
(( found )) || exit 0

REASON="Your reply drafts a message for the user to send, answering a message they just pasted, and you asked them nothing since (claude/rules/drafting-messages-for-the-user.md). Check the pasted message now: if it asks the user anything they have not answered in this session (availability, a time, yes or no, a figure, a preference), the draft must not decide it. Ask with AskUserQuestion, then draft from their answer. Check every line of the draft is something the user said or has written before: no stock lines they do not use. If nothing was unanswered and nothing was added, end the turn with no further text."
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
