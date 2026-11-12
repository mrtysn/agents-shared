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
