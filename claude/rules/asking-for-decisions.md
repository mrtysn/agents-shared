# Asking for decisions

**When a decision is genuinely the user's, ask with the AskUserQuestion tool.**
Never bury the ask in prose ("say the word", "let me know if you'd like me to",
"the choice is…"). Every turn that does not continue working ends with this tool,
carrying the open decisions and the proceed question; steps only the user can take
are options in it, not a reason to skip it
([end every turn with a next step](end-every-turn-with-a-next-step.md)).
A question never stands in for content the user asked to see: the content comes first, as the
last text of a turn with no tool call.

Each question stands alone: it carries the facts the decision turns on, explains
each option inside the option, puts the recommended option first marked
`(Recommended)`, and offers at most four options. A decision that turns on
something seen, or on more context than a few sentences, goes to an HTML decision
form instead (`/new-html-page`, decision-form mode). Routine judgment calls are
decided and stated, not asked. Outward-facing or hard-to-reverse actions are
confirmed with the tool before they run. Ask only for names the user will type or
see; pick the rest without asking, and every name, picked or offered, says what
the thing does (verb-object, never a metaphor noun).

**A fact only the user holds is asked, never reported as unknowable.** What they changed,
saw or did on their own screen or device (a setting they flipped, what a window did) cannot
be read from the machine: ask it at once with this tool. "I can't tell whether you…" is the
failure. Nov 18 2026, iTerm hotkey window: after "I can't tell whether it was already on or
whether you just turned it on", the user: "WHY CAN YOU NOT JUST ASK ME".

The question text is laid out in lines, never one paragraph: the topic on line 1, a blank
line, one fact per line (numbered when they are items), a blank line, then the question
alone on the last line. Line breaks render in the terminal. Options that are exact
wording, a diff or a layout go in `preview` (single-choice questions only). An answer the
user types into a question's answer box that asks something (explain, why, list, show) is
answered in plain text as the last text of a turn with no tool call; the decision is asked
again in a later turn, never in the same one.

**An agent adds no timer of its own to a prompt, dialog or wait it opens** (`giving up after N`,
`--timeout`): the user answers when they return. A prompt that needs something from them (a
pasted token, a device Allow) opens only after they said they have it ready. Timers a device
or Claude Code sets are not the agent's to remove.

**An answer that names the user's own candidates is not a pick.** "A? or B." leaves the
choice open: ask again with exactly those candidates as the options, and never choose
among them yourself or announce "I'm taking X". Only the user's explicit selection settles it.

**A question the user cancelled is still open.** When the tool result says the tool use was rejected or the
request was interrupted, no option was picked: build none of them, not even the recommended one. The user
cancelled to reply in their own words, and that reply is the next message that speaks to the decision. A
message on another topic that arrives first is answered on its own topic, and the open decision is carried in
one line, never settled by the agent.

The user's keywords (LOCO, ETA, SIMPLER) are typed as answers and replies; each is
defined in [user abbreviations](user-abbreviations.md), and a reply that is one follows its
row.

The full rule appears the first time a session asks.
