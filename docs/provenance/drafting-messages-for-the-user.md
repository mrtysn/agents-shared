# Provenance: Drafting messages the user sends

Why [the rule](../../claude/rules/drafting-messages-for-the-user.md) exists.

2026-10-25. The user pasted a message that asked whether a meeting time worked. The agent
answered with a ready-to-send draft saying the time worked, without asking the user, and
closed with a stock line the user does not use. Earlier drafts in the same session had
added claims and asks the user had not given.

Question handling, stated desires, asking for decisions and working style were all
loaded when it happened; none of them speaks to words put in the user's mouth. A rule
loaded at launch had already been ignored, so the rule comes with a Stop hook that
looks at the reply itself: a prompt-time hook would not have fired, because the
prompt was an image with no text.

A blind review shaped three choices: the test is "an unanswered question in the message
means no draft yet", the ask goes through AskUserQuestion, and "a question about a
draft is answered, not re-drafted" went into question handling instead of here.

2026-11-12. A survey of the user's corrections to drafts over three weeks found the same
patterns recurring after the rule existed: asks for things already sent, open messages left
unanswered, pressure the user never set, several asks lumped into one, promised deliverables
that were not ready, lines about the message itself, extra mentions, and a stiff register.
The user confirmed each new line on a decision form. The promise line also covers what the
user chooses to reveal: a recipient sees only what the user decided to tell them.
