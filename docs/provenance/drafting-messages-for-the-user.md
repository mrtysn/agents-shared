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
