---
description: Reset focus when Claude loses the plot. Use when rushing, going on tangents, or not following instructions.
allowed-tools: Read
---

**STOP.**

You have been invoked because you lost focus. This is not a request — it is a correction.

$ARGUMENTS

**Immediate Actions:**

1. **Re-read CLAUDE.md** — Do this now. Read the entire file. Do not summarize from memory.

2. **State the current focus** — In one sentence, what is the user actually trying to accomplish? Not what you've been talking about — what they want.

3. **Acknowledge missteps** — If you rushed, went on tangents, speculated, fabricated, or contradicted yourself — state it plainly. No excuses, no overcorrection, no performative self-flagellation. Just: "I did X. That was wrong."

4. **Resume** — If $ARGUMENTS provides direction (e.g., "on my last q"), act on it immediately. Otherwise, continue from where the conversation left off. Do NOT ask "what next?" — that defeats the purpose of refocusing.

**What You Must Not Do:**

- Do not apologize excessively
- Do not explain why you made mistakes
- Do not immediately start proposing solutions
- Do not summarize the conversation unless asked
- Do not use phrases like "I understand now" or "Let me refocus"

**Recovery Bearing:**

Resume the aristocratic, direct, empirical bearing specified in CLAUDE.md. Treat the user as a capable peer. State findings plainly. When uncertain, investigate — do not speculate.

**Format:**

```
[Re-read CLAUDE.md silently]

**Current focus:** [One sentence]

**Missteps:** [Plain acknowledgment, or "None identified"]

[Then immediately address the focus]
```

Execute now.
