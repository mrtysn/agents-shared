# Provenance: "Read this" means read the contents

Why [the rule](../../claude/rules/read-means-read-the-contents.md) exists.

Oct 28 2026, notebook: the user pasted a screenshot of a Telegram export, `result.json`
(1.4 MB, 913 messages), with "read this file". The session ran a python script that
counted message kinds and printed the first and last few lines, summarised the counts,
then asked what the user wanted from it. The user: "when I tell you to read something,
you must read it. but look at what you did instead", then, at the meta level, "fix your
behavior". The file holds about 270k tokens as text; it was read in chunks only after
the correction.
