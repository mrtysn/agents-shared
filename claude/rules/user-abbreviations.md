# The user's abbreviations

**Each is a single whole word, in any case, typed alone or as the first word of a
message followed by punctuation or a line break.** A leading `;` (`;loco`) forces the
keyword reading and is never required. A word typed as an answer to a question reaches
the agent as text, not as a command, so it must be known from a rule like this one.

This table is the one home of each word: what it means and what the agent does. One row
per word, one line per row, no `|` inside a cell.

| Word | Means | What the agent does |
|---|---|---|
| LOCO | lack of context: the last question or message left out what is needed | Send it again at once with what the thing is, why it is asked now and what each option does, in the text itself; do not defend the first version. The same for a lone "what", "i dont get X" and "what does X mean" about something just written; after an interrupt, a lone "what" asks what you were doing, so say that. |
| ETA | when the running work should finish, with its basis | Read the running work's live state first (it may have failed or hung), then answer with the duration the no-time-estimates line in communication-style.md allows (a counted remainder times a measured rate, all stated), or with what is done, what is left and what it waits on. |
| SIMPLER | rewrite in plainer words, keeping every piece of information | Rewrite the last answer in plainer words and keep every piece of information. Deleting the substance and returning the fragment answers a smaller question. If something must be dropped to be readable, say what in one clause. |

A new word is one row here.
