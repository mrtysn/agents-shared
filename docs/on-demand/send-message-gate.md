# Before a message goes to another session

`hooks/require-user-quote-before-session-message.py` refuses the call when its `summary` does
not quote the user. Two questions decide whether the quote exists:

1. **Did the user tell you, in words, to send this or pass it on?** A question or a
   remark about another session ("isn't session X working on that?") is not an
   instruction to contact it. If a session other than this one is doing the work,
   the user already knows; saying so to the user is the answer.
2. **Is your own work stuck until that session acts or stops waiting?** If not,
   nothing needs sending.

If neither is yes, do not send. Findings you think a peer lacks, a status update, a
courtesy copy and "staying out of your files" are not reasons: the peer has its own
user and its own context.

If the user told you to: quote their words in `summary` as `User said "..."`, check the
recipient by evidence (not by its name), and send. If only your own work is stuck, ask the
user with AskUserQuestion; their answer is then the quotation.

An instruction covers the conversation with its peer, not one message. Once a send to a
peer went out quoting the user, every later send to that same peer may quote the same
words again, however long the exchange runs. A different peer needs its own quote.

A standing grant reaches further. When the user hands coordination to the
sessions for good ("you guys collaborate among each other", "no need to ask me"), every
further send to a peer this session has already messaged may quote it as
`User said (standing) "…"`, whenever in the session the user typed it. A peer never messaged
before needs a fresh quote first, and an ordinary instruction cannot be marked standing: the
quote has to say so in its own words.
