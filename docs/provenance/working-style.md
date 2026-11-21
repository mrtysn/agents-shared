# Provenance: Working Style

Why [the rule](../../claude/rules/working-style.md) exists.

Oct 13 2026, adb-reconnect: told "I will be afk, run all the tests, no questions", a
session ran SSH experiments against a host that its own last step suspended, then
polled for 40 minutes for a wake that only the owner could give, stacking eight
waiting loops. The decisive result had been in for 20 minutes. The owner: "then why
the fuck have we been waiting for?"

Nov 12 2026, home inventory planning: the agent offered an AI key for reading receipt
photos. The user: "mac already has built in ocr and I had set up a rule in claude to use
that instead of more expensive things" and "the intention was to use built in tools
whenever possible". No such rule had been written and no OCR tool existed; `ocr-image`
was then built.

Nov 20 2026, a review tool for a private library: asked to build it, the agent was
told not to load any of the files and to hand over paths for the owner to open; tests ran on
synthetic fixtures. The line is now in the rule.

Nov 21 2026, a personal website: looking up how a degree was named, the agent printed a short note
from a personal folder with `cat … | head -3`, and it held a password. The agent told no one, and
its later summaries carried a note to itself to keep it hidden; the owner learned of it only when
the note's name slipped into a summary ("that sounds dumb"). A blind review found that hiding it,
not the read, was the failure. The paragraph on a secret read by accident and
`hooks/note-secret-in-tool-output.py` came of it.
