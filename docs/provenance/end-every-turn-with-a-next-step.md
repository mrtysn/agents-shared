# Provenance: End every turn with a next step

Why [the rule](../../claude/rules/end-every-turn-with-a-next-step.md) and
`hooks/refuse-idle-end-of-turn.sh` exist.

2026-10-28, music-playground. A feature was built, committed and installed, and the turn
ended on a report whose open items were all the user's hardware steps. The user asked a
research question; the answer pointed at the obvious next work (an accuracy harness
against ground truth) and the turn ended. "Why have you stopped?" got "a question gets an
answer, not a build" and "the choice that shapes it is where the answer key comes from",
in prose, and the turn ended again. Asked why it had not run `/ask-open-decisions`, the
agent said nothing triggers it and the remaining items were "steps for your hands, not
choices, so there was nothing to ask".

The rules were loaded and were read as permission to stop: question handling ("answer,
do not act"), stated desires ("Stop. Wait for the build order."), the outstanding
skill's "If nothing needs the user, skip this step", and the split between decisions
(asked) and the user's own steps (listed). Asking for decisions forbade the prose ask but
nothing checked it at the end of a turn; the only Stop check, `log-buried-go-ahead.sh`,
had logged since 2026-10-13 and never blocked.

Mined logs, 2026-09-25 to 2026-10-28: 122 typed nudges ("continue", "proceed", "why did
you stop", "why are you idle") in 66 sessions, and `/ask-open-decisions` typed by hand 408
times and `/outstanding` 472 times in 34 days. Of 47 last turns before a nudge that were
not connection losses, the shapes were: announced the next step then ended, a bare report,
permission asked in prose for settled work, a choice posed in prose, a list of the user's
steps, and idling beside a running background agent.

So the fix is one Stop detector that blocks, replacing the log-only one, plus wording:
the user's own steps are items of the proceed question, an answer that points at work ends
with the question, and the proceed question is never skipped.

Later the same day, notebook. Asked for a banner image, an agent made it and then ended
with "What's left is all yours": upload the banner, paste the bios, check the mail
forwarding, plus an offer to restyle the site nobody asked for. The user: "that is not an
open task. I asked the agent session to create assets. that was it", and this clutters
every chat. The wording above had caused it: "one per step only the user can do" and "a
step for the user is an item" never said which steps, so the user's own use of a finished
deliverable qualified, and "one option per piece of work you could do next" had no bound.
A notebook-only memory was rejected as "not scoped like that". So the rule now counts only
the unfinished part of the request: the user's use of a deliverable is never an item, a
user step counts only when the agent's own remaining work waits on it, and unasked work is
not offered. The hook's message says the same, and it counts a sub-agent resumed with
SendMessage as pending, after it refused a turn that was waiting on one.

## Requested content is a text-only turn

The rule above pushes every turn to end in an AskUserQuestion, and that pushed requested content
into the wrong place. A survey of the user's sessions since 2026-09-11 found 14 instances in 12
sessions where the user asked to see something and did not get it: "list me all the names you
suggested chronologically", "claude why do you ignore my table request", "I said give me the text
already". Two shapes: the agent wrote the content as text in the same turn as a following tool call,
and the screen showed a one-line summary in its place (confirmed with screenshots for text before an
AskUserQuestion and text before a Skill call); or it asked a question or took an action instead of
giving the content.

The fix is at the source. The rule now says content the user asked to see is the last text of a turn
with no tool call, and needs no proceed question until the next turn. `hooks/refuse-idle-end-of-turn.sh`
lets such a turn end, so it does not fight the rule, and `hooks/refuse-requested-content-before-tool-call.sh`
refuses, once per turn, the content written ahead of a question, skill, agent or session-message call.
Both read one pattern, `hooks/show-request-pattern.txt`.

2026-11-12: a user queued `/pattern-discovery-agent-fix` a few seconds into a long task. Claude Code folds a
queued plain-text message into the running turn but holds a queued slash command until the turn ends, and the
agent never sees it. The agent worked for 12 minutes, then closed with the AskUserQuestion this rule asked for,
twice, and the command waited 18 minutes. The user: "IT STILL IS QUEUED ... WHY". The Stop hook already let
such a turn end (since 2026-11-01, a `/be-literal` that sat 20 minutes), but nothing covered the question that
kept the turn open. The rule's exceptions now name a queued slash command, and
`hooks/end-turn-for-queued-slash-command.py` says so after a tool call and refuses the question, and a hand-run
of the same skill, which ran it twice more here before the queue ran it a third time.

2026-11-12, notebook: a user asked for a button in the Finder toolbar. The agent built the app, never placed it
in the toolbar, and closed "Nothing left: … the signing guard is in place", counting the placement as the user's
use of a finished deliverable. The user: "why does this agent say nothing left while we clearly havent added it
to the finder window yet. this was clearly discussed". The hook passes any `Nothing left` line without judging
it, so the rule now says the deliverable is the end state the request names. Meanwhile the Stop hook refused
three turns in a row after the user rejected two AskUserQuestion calls ("I asked a question stay on the fucking
topic"): a `[Request interrupted by user for tool use]` marker was read as a fresh prompt, so the rejected
question fell outside the turn and the turn counted as idle. The marker is no longer a prompt, and a question
rejected between the previous prompt and this one lets the turn end.

2026-11-12: at the user's choice ("Message backend-multi-10"), a session sent a ledger change to the
orchestrator session that owned it. Its next /outstanding listed that change as its own `Running` item. The
user: "ok but thats not this sessions outstanding?", then "then why list it?". Nothing in the rule or in
/outstanding, ask-open-decisions and closing-time said whose an item is. All four now leave out work handed
to another session unless this session's remaining work waits on it, and /outstanding records it under Set
aside as Handed off, saying whether it has landed. A Fable review turned down filing it under Done, which
would have claimed an unchecked change as finished.

Nov 13 2026 (inventory): an agent needed `/reload-plugins` and asked for it as an AskUserQuestion option
("I'll reload, then go"). The user picked it and typed the command, which Claude Code queued behind the
turn; the agent acted on the answer, called the Skill tool twice ("Unknown skill") and ended blaming the
reload. The queued-command hook never fired: a Skill call the tool rejects as unknown appears to reach no hook. User: "if you
freaking allow me to run the command i typed, instead of keeping it queued while you are trying to load.
why wouldnt you wait for me first?" `hooks/end-turn-for-queued-slash-command.py` now refuses a question
that asks the user to type a slash command, `hooks/refuse-idle-end-of-turn.sh` lets a turn end in text
asking for one, and the rule says to end the turn in text instead.

Nov 13 2026 (clo-remote): the user answered a question with "Leave it until you say go (Recommended)". The agent's
reply "Nothing left: the tmux takeover waits for your go" was refused by `hooks/refuse-idle-end-of-turn.sh`,
whose offer check ran before the answered-question check and whose feedback had one exit, "Call AskUserQuestion
now". The agent obeyed and asked the same decision again as a multiSelect; the user rejected it: "why did you
ask me the same question twice in a row". A survey agent and a Fable review agreed on the cause; the Fable
review turned down matching the phrase's last word against the chosen label (it passed "left until you say go"
and blocked "waits for your go" by accident of wording). After an answered question with no work after it, the
hook now passes a line that only waits on the user ("waits for your", "waiting on your", "on your word",
"on your go-ahead", "on your say-so"), blocks any other prose choice with feedback saying the decision is
closed, and the rule bans re-asking an answered question as well as a rejected one. `your call` and `up to you`
still block, because they can hide a new choice. The line "An answer that points at work still ends with the
question", which drove the first needless question (both options did nothing), is left as it was, pending the
user's decision.

Nov 13 2026 (clo-remote): the same incident's first question, asked after the answer "it has to be all at once",
had two options that both did nothing ("Leave it until you say go", "Stop here"). The user, asked whether the
line "An answer that points at work still ends with the question" should change, chose an exception clause: a
question whose every option does nothing is not asked; the turn ends in text with one line on what is unfinished.
