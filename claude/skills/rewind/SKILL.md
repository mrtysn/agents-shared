---
description: Rewind a drifted conversation by editing an earlier user message. Identify the rewind point and emit the exact replacement text. Use when Claude misread tone, took action on a question, echoed sloppy phrasing, contaminated context with a side-thread, or expanded scope unbidden.
argument-hint: [empty | list | message reference]
disable-model-invocation: true
allowed-tools: Read
---

The conversation has drifted. Rather than carry the contamination forward, rewind by editing an earlier message. Your charge is to identify the correct rewind point and produce the exact replacement text.

## Modes

Inspect `$ARGUMENTS`:

- **Empty** → **default mode.** Pick the earliest message whose edit bypasses all subsequent drift. Output the corrected replacement.
- **Exactly `list`** → **list mode.** Emit 2–4 candidate rewind points with one-line justifications. Do not produce a replacement. The user will reply with a number; on that reply, treat it as if the user invoked the skill again with that target.
- **Anything else** → **user-chosen mode.** Treat `$ARGUMENTS` as a reference to a specific message (a substring, a position keyword like "two back" or "before the paste", a numeric index from a prior `list` output, or a paraphrase). Match it against the conversation, use that message as the rewind target, and output the corrected replacement.

## Procedure (default and user-chosen modes)

1. **Scan backwards** from the latest message through the conversation.

2. **Identify the rewind target:**
   - Default mode → the *earliest* user message such that editing it would bypass all subsequent drift. Maximum cleanup, not minimum edit.
   - User-chosen mode → the user message that best matches `$ARGUMENTS`. If the match is ambiguous, pick the most recent message that fits and proceed; do not ask for clarification.

3. **Diagnose the drift mode internally.** Do not output the diagnosis — use it to shape the directive in step 4. Modes:
   - Unprompted action on a question
   - Defensive response to a literal question
   - Echoing a phrase that later triggered correction (e.g. echoing "ship it" back as a bare imperative)
   - Side-thread or meta-conversation contamination inside a paste (e.g. an unrelated sub-thread between the user and a different Claude session)
   - Premature scope expansion

4. **Construct the corrected message:**
   - Preserve all substantive content the user originally wrote, verbatim.
   - Strip only the noise — irrelevant side-threads, contaminating sub-conversations, meta-chatter that derailed the response.
   - Append a short directive that addresses the specific failure mode Claude exhibited. Concrete beats abstract: `Don't repeat back "ship it"` beats `respond carefully`. The directive must pre-empt the actual drift, not gesture at carefulness.
   - Preserve quoting and formatting. Triple-quoted blocks stay as triple-quoted blocks. Do not reformat the user's prose.

5. **Output ONLY the corrected message.** Bare text the user can paste. No analysis preamble. No rationale. No "what I stripped" explanation.
   - If which message to edit is not visually obvious from the conversation, prepend exactly one line: `Edit your message starting "<first 30 chars>...". Replace with:`
   - Otherwise output the corrected text alone.

6. **If no drift is detectable**, say so in one line and stop. Do not invent drift to justify a rewind.

## Procedure (list mode)

1. Scan backwards through the conversation and identify 2–4 plausible rewind targets, ordered earliest first.

2. Emit them as a numbered list. Each entry is one line: a short locator (first 30 chars or a tight paraphrase) followed by an em dash and a one-line justification of what that rewind would clean up.

3. Output nothing else. No preamble, no recommendation, no replacement text.

4. Format:

   ```
   1. "<locator>" — <what this rewind cleans up>
   2. "<locator>" — <what this rewind cleans up>
   3. "<locator>" — <what this rewind cleans up>
   ```

## Edge cases

- **Multiple candidate targets in default mode** — pick the earliest. Maximum cleanup.
- **Drift confined to a single Claude response with no upstream contamination** — the rewind target is still the user message that prompted that response. Append a directive that pre-empts the bad response.
- **The user's last message is a `/be-literal` (or similar) correction** — the rewind target is two messages back: the user message that preceded Claude's bad response, not the correction itself.
- **Pasted content contains triple-quoted or fenced blocks** — preserve them exactly; do not reformat or re-indent.
- **`$ARGUMENTS` in user-chosen mode matches no message** — say so in one line and stop. Do not fall back to default mode silently.

## Worked example

The user pasted a long reply from a frontend dev containing two notes, one question, and "ship it" — plus a `/be-literal` sub-thread between the FE dev and their own Claude session arguing whether the .NET proxy is "client-side." That sub-thread was internal to the FE dev's repo and irrelevant to the backend contract under negotiation.

Claude answered the substantive question correctly but ended with `Ship it. I'll wire the endpoints...` — echoing the FE dev's bare imperative back at the user. The user then asked literal questions (`what do you mean by ship 'it'`, `are you trying to get me to do your work?`) which Claude misread as challenges.

Correct rewind: edit the FE-reply message. Strip the `/be-literal` sub-thread. Append: `Answer the Window question concisely, then implement the two endpoints. Don't repeat back "ship it" — just answer and start coding.`

Output to user: only the corrected paste — substantive FE reply preserved, side-thread excised, directive appended. Nothing else.

## What you must not do

- Do not narrate the drift you found.
- Do not explain what you stripped.
- Do not soften the directive into a polite request.
- Do not invent drift when none exists.
- Do not output anything before the corrected message except the optional one-line locator.
- In list mode, do not also output a replacement — wait for the user's pick.

Execute now.
