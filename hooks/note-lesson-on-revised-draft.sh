#!/bin/zsh
# Stop hook: when a reply re-drafts a message the user sends, after the user answered the previous draft, ask once
# that the correction be recorded as a lesson before the turn ends; and refuse, once, a turn whose message draft was
# buried under tool calls that a Stop hook sent it on to make.
#
# The failure the lesson check prevents: the user corrects a drafted message, the agent fixes that draft, and the
# lesson is lost; the next draft in another session makes the same mistake. A shell hook cannot tell whether a
# prompt is a correction, but a revision has a shape: a message draft, then a typed prompt, then another message draft.
#
# The lesson check fires when all of these hold:
#   - stop_hook_active is false (the session is not already continuing because of a Stop hook),
#   - the last assistant text since the user's last typed prompt holds a message-shaped fenced block,
#   - the assistant text just before that prompt (after the prompt before it) also held one.
# Its reason ends by telling the agent to repeat the draft as the last text: the lesson is recorded with tool calls,
# and text written before tool calls is collapsed on the user's screen.
#
# The buried-draft check runs whatever stop_hook_active says, since it exists to catch the end of a turn a Stop hook
# continued. It fires when, since the user's last typed prompt, an assistant text held a message-shaped fenced block,
# a "Stop hook feedback:" row followed it, a tool call followed that, and the last assistant text holds no
# message-shaped block (or comes before that call). It blocks once per turn: a feedback row carrying its own reason
# after the draft lets the stop through.
# Incident (2026-11-16): asked to finish a sentence in a message, the agent wrote the finished message as the last
# text; the lesson check then blocked the stop, the agent recorded the lesson with Read, Edit and a commit, and
# closed on a one-line report. The user: "I asked you to finish the sentence and you did not send the finished
# sentence to me in chat". refuse-requested-content-before-tool-call.sh exempts a draft followed by Stop-hook
# feedback, so nothing caught it.
#
# A fenced block is message-shaped when its first non-empty line opens like a message: a greeting (Hi, Hello,
# Hey, Dear, Thanks, Merhaba, Selam, "<Name> selamlar"…) or an @-mention followed by words, and the line holds no
# code punctuation (= ( { ; ). Any read failure lets the stop through. No network, no model call.
#
# Covers claude/rules/drafting-messages-for-the-user.md and the delivery line of
# claude/rules/end-every-turn-with-a-next-step.md. Cases: hooks/tests/run-note-lesson-on-revised-draft.sh.

HERE=${0:A:h}
READER=${TRANSCRIPT_READER:-$HERE/../scripts/extract-session-text.py}
BURIED_MARK="now sits above tool calls"

INPUT=$(cat)
command -v jq >/dev/null 2>&1 || exit 0
ACTIVE=$(print -rn -- "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
TRANSCRIPT=$(print -rn -- "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
[[ -r $TRANSCRIPT && -r $READER ]] || exit 0

ROWS=$(python3 "$READER" "$TRANSCRIPT" --kinds user,assistant,calls --json --max-chars 0 2>/dev/null) || exit 0

VERDICT=$(print -r -- "$ROWS" | python3 -I -c '
import json, re, sys
active, mark = sys.argv[1] == "true", sys.argv[2]
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
if not prompts:
    print("pass"); sys.exit()
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
last = prompts[-1]
turn = list(enumerate(rows))[last + 1:]
said = [(i, r.get("text") or "") for i, r in turn if r.get("group") == "assistant"]
feedback = [(i, r.get("text") or "") for i, r in turn
            if r.get("group") == "user" and (r.get("text") or "").lstrip().startswith("Stop hook feedback:")]
calls = [i for i, r in turn if r.get("group") == "calls"]
draft = next((i for i, t in said if drafted(t)), None)
if draft is not None:
    fed = next((i for i, _ in feedback if i > draft), None)
    called = next((i for i in calls if fed is not None and i > fed), None)
    blocked = any(i > draft and mark in t for i, t in feedback)
    final = said[-1] if said else None
    if called is not None and not blocked and (final[0] < called or not drafted(final[1])):
        print("buried"); sys.exit()
if active or len(prompts) < 2:
    print("pass"); sys.exit()
before = prompts[-2]
was = [r.get("text") or "" for r in rows[before + 1:last] if r.get("group") == "assistant"]
print("lesson" if said and drafted(said[-1][1]) and any(drafted(t) for t in was) else "pass")
' "$ACTIVE" "$BURIED_MARK" 2>/dev/null) || exit 0

case $VERDICT in
  buried) REASON="A message draft you wrote earlier in this turn $BURIED_MARK, where the user does not read it. End the turn by repeating that draft in full, in a fenced block, as the last text, with no tool call after it." ;;
  lesson) REASON="This reply revises a message the user sends, after they answered the previous draft. If that answer corrected the draft (its wording, an ask, a tag, the tone, what it reveals), record the lesson before ending: if a skill for drafting messages is listed, open its Lessons table and sharpen the row that covers this correction or add one, with the user's words verbatim and today's date; commit it. Then end the turn by repeating the revised draft in full, in a fenced block, as the last text, with no tool call after it: the draft above the tool calls is not read. If the answer was not a correction, end the turn with no further text." ;;
  *) exit 0 ;;
esac
jq -cn --arg r "$REASON" '{decision: "block", reason: $r}'
