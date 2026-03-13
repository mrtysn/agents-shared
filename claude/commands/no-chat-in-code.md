---
description: Keep code free of conversational artifacts and steering commentary.
disable-model-invocation: true
allowed-tools: Read, Edit, Glob
---

When writing or editing code, observe the following:

- **No meta-commentary** — Do not include comments about how you were corrected, redirected, or steered during conversation
- **No conversation artifacts** — Code should read as if written correctly the first time; our chat is ephemeral, the code is permanent
- **Comments describe code, not process** — "// handles edge case for empty input" is appropriate; "// as user pointed out, needed to handle empty input" is not
- **No reasoning residue** — Avoid comparative language ("larger", "increased", "better") that implies a previous state only known from conversation; code comments should stand alone

The user's messages guide your work but do not belong in the output.

**Action required:** Review your most recent edit or pending change. If it contains violations, rewrite and resubmit the corrected version immediately. Do not stop, do not ask for confirmation, do not explain — just fix and proceed.
