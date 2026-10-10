# Search for a term you do not know

**When the user uses a name, term or acronym you do not recognise, search for it
before answering.** Do not report that you could not find it locally, and do not
ask the user what it means. A short web search settles most such terms in one call.

A local search (`which`, `brew list`, `ls ~/dev`) only shows whether something is
installed under that name. It cannot say what the name refers to, and a negative
result there is not an answer.

## What to do

1. Run a web search on the term, with its context words (`Laya JEV decision model`).
2. If the first result is thin, send a second query with different wording.
3. Then answer the user's actual question, with what the term means stated in a clause.
4. Ask the user only if two searches still leave the term unresolved, and say what
   the searches returned.

Searching is read-only and this rule overrides the habit of stopping at "I don't
know what X is". Third-party blogs are often affiliated with what they describe;
say so when the answer rests on them.

## Provenance

Oct 10 2026, notebook: asked "do we have laya installed as jev?", the session
searched the machine for `laya` and `jev`, found nothing, and replied that it did
not know what "jev" meant. Jev is TypeSafe's hosted decision API and Laya is an
open local model that serves the same wire format, so the answer was yes. The
user: "search online for stuff you dont know man... why are agents choosing to
leave themselves in the dark about a term".
