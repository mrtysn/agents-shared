#!/bin/zsh
# Stop hook: when a reply re-drafts a message the user sends, after the user answered the previous draft, ask once
# that the correction be recorded as a lesson before the turn ends.
#
# The failure this prevents: the user corrects a drafted message, the agent fixes that draft, and the lesson is
# lost; the next draft in another session makes the same mistake. A shell hook cannot tell whether a prompt is a
# correction, but a revision has a shape: a message draft, then a typed prompt, then another message draft.
#
# It fires when all of these hold:
#   - stop_hook_active is false (the session is not already continuing because of a Stop hook),
#   - the last assistant text since the user's last typed prompt holds a message-shaped fenced block,
#   - the assistant text just before that prompt (after the prompt before it) also held one.
# A fenced block is message-shaped when its first non-empty line opens like a message: a greeting (Hi, Hello,
# Hey, Dear, Thanks, Merhaba, Selam, "<Name> selamlar"…) or an @-mention followed by words, and the line holds no
# code punctuation (= ( { ; ). Then it blocks once with {"decision":"block"}. Any read failure lets the stop
# through. No network, no model call.
#
# Covers claude/rules/drafting-messages-for-the-user.md. Cases: hooks/tests/run-note-lesson-on-revised-draft.sh.

HERE=${0:A:h}
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
[[ $(print -rn -- "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null) == true ]] && exit 0
TRANSCRIPT=$(print -rn -- "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[[ -r $TRANSCRIPT && -r $READER ]] || exit 0

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant --json --max-chars 0 2>/dev/null) || exit 0

VERDICT=$(print -r -- "$ROWS" | python3 -I -c '
import json, re, sys
rows = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if not r.get("sidechain"):
        rows.append(r)
prompts = [i for i, r in enumerate(rows)
           if r.get("group") == "user" and r.get("origin") == "human" and not r.get("meta")]
if len(prompts) < 2:
    print("pass"); sys.exit()
last, before = prompts[-1], prompts[-2]
def texts(a, b):
    return [r.get("text") or "" for r in rows[a + 1:b] if r.get("group") == "assistant"]
OPEN = re.compile(r"^(hi|hello|hey|dear|thanks|thank you|merhaba|selam|selamlar|good (morning|afternoon|evening))\b"
                  r"|^[^\W\d_]+ (selamlar|merhaba)\b|^@[^\W\d_][\w.]*[ ,]+[^\W\d_]", re.I)
def drafted(text):
    inblock, first = False, None
    for line in text.splitlines():
        if line.startswith("```"):
            if inblock and first is not None and OPEN.search(first) and not re.search(r"[=({;]", first):
                return True
            inblock, first = not inblock, None
            continue
        if inblock and first is None and line.strip():
            first = line.strip()
    return False
now = texts(last, len(rows))
was = texts(before, last)
print("block" if now and drafted(now[-1]) and any(drafted(t) for t in was) else "pass")
' 2>/dev/null) || exit 0
[[ $VERDICT == block ]] || exit 0

REASON="This reply revises a message the user sends, after they answered the previous draft. If that answer corrected the draft (its wording, an ask, a tag, the tone, what it reveals), record the lesson before ending: if a skill for drafting messages is listed, open its Lessons table and sharpen the row that covers this correction or add one, with the user's words verbatim and today's date; commit it. If the answer was not a correction, end the turn with no further text."
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
