# Drafting messages the user sends

**A message or document drafted for the user to send says only what the user has said.**
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
- **One voice, chosen first.** Before writing, settle who speaks and to whom: the voice
  the user's earlier sent documents to that reader use, else the one the user picks. Keep it
  in every line: no outside narrator on the user's own work.
- **Every reference has an owner.** No "their", "it" or "as planned" the recipient cannot
  resolve from that sentence alone; name the person or thing. Before showing a draft, reread
  it as the recipient, and reread every sentence a revision touched.
- **The whole thread first.** Before drafting, read every message in the thread: every
  channel, file and screenshot the user gave. Answer every message still open to the
  user, and never ask for something already sent.
- **No pressure.** No deadline, urgency or "let me know when" that the user did not set.
- **One precise ask per item.** Each ask names one system or thing, exactly what is
  needed from it, and why. Ask only what the recipient alone can answer; what the code or
  a document will show is not asked.
- **Promise only what is ready, and reveal only what the user chose to.** No date,
  deliverable or commitment the user has not made in this conversation, and nothing about
  the user's own work, tools or plans that they have not chosen to tell this recipient.
- **No meta lines or filler.** No lines about the message itself ("the follow-up I
  promised"), and no references the recipient has to decode ("as you asked").
- **Address only who needs it.** No @-mention of someone already following the
  conversation unless the line is for them alone.
- **Wording by the reader's role.** In a work folder, look up each recipient's role in
  its `notes/people.md`. Write to people who build in technical terms; to people who run
  the business, say what each thing does for the product, the users or the money. A message
  to both leads with the outcome. A folder whose people file has no "Company structure"
  section gets one before the first draft: who decides, who builds, who coordinates, and
  which channel reaches whom.
- **Plain register.** Plain words, no pretentious phrasing, no barrage of questions; soft
  asks ("have a look") over demands ("please confirm").
- **A drafting skill, when one is listed.** If the session lists a skill for drafting
  messages, load it before the first draft.
- **Collaborative and kind.** Write as a teammate among peers: shared work is "we" and
  "together", and an ask says what it helps the work do. No line casts the recipient as
  someone to be sorted or managed ("so I know where to start with each of you"); that
  reads as condescending however it was meant.
- **Turkish without the circumflex.** Write "hala", "halihazırda", "kar", never "hâlâ",
  "hâlihazırda", "kâr": the user's written Turkish does not use â, î or û.
- Copy-ready text goes in a code block.

A Stop hook (`hooks/refuse-unasked-draft-reply.sh`) refuses, once, a drafted reply to
a pasted message when nothing was asked since the paste. `hooks/note-lesson-on-revised-draft.sh` (Stop)
asks, once, that a correction to a revised draft be recorded as a lesson in the drafting
skill's Lessons table.

Provenance: [docs/provenance/drafting-messages-for-the-user.md](../../docs/provenance/drafting-messages-for-the-user.md).
