# Drafting messages the user sends

**A message drafted for the user to send says only what the user has said.**
It goes out under their name, so every word in it is a claim they make.

- **Only what they gave.** No claims, numbers, feelings, compliments or extra
  asks they did not state.
- **Never answer for them.** If the message being answered asks something the
  user has not answered in this session (availability, a time, yes or no, a
  figure, a preference), there is no draft yet: ask with AskUserQuestion, then
  draft from the answer.
- **Their voice.** Read their sent messages in that thread before drafting.
  No stock lines ("See you then", "Looking forward", "Hope you're well") unless
  they write that way.
- Copy-ready text goes in a code block.

A Stop hook (`hooks/refuse-unasked-draft-reply.sh`) refuses, once, a drafted reply to
a pasted message when nothing was asked since the paste.

Provenance: [docs/provenance/drafting-messages-for-the-user.md](../../docs/provenance/drafting-messages-for-the-user.md).
