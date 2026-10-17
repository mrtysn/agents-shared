# Provenance: Restate hidden output in your own reply

Why [the rule](../../claude/rules/restate-hidden-output-in-replies.md) exists.

Sep 2026: after a discovery agent's report, the reply said "the result is above",
and the user answered with a screenshot: "what is 'above'?". A transcript survey
(`scripts/find-invisible-output-claims.py`) found the same shape earlier that
month: a background agent's findings referenced but never shown, until "show me
what you grabbed so far". Counting long tool output as hidden too
(`--tool-output-chars 600`), the survey found 14 such references and 18 paired
"where?"/"show me" replies across eleven projects in September 2026 alone; "as
reported" was the most common phrasing.
