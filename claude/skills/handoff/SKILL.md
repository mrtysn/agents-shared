---
description: Craft a handoff message for a new session. Use when context must survive session boundaries. Pass a session UUID to consolidate a handoff from a past session instead of the current one.
argument-hint: [optional notes to emphasize, OR a session UUID]
allowed-tools: Read, Glob, Grep, Agent
---

The session draws to a close, yet the work remains unfinished. You shall compose a handoff message for your future self — a missive that shall be delivered by the user into a fresh session.

$ARGUMENTS

---

## Mode Detection

Inspect `$ARGUMENTS`. If — and only if — it is exactly a UUID in 8-4-4-4-12 lowercase hex form (e.g. `ec810080-e08b-4ea8-96b0-38b1fc5508be`) with no surrounding prose, enter **past-session mode**. Otherwise, enter **current-session mode**.

### Past-session mode

The transcript of a prior session must be summarized without polluting your own context. Delegate the read to a sub-agent.

Spawn a `general-purpose` sub-agent with a self-contained prompt instructing it to:

1. Locate the transcript file at one of:
   - `~/.claude-personal/projects/*/<UUID>.jsonl`
   - `~/.claude/projects/*/<UUID>.jsonl`
2. Read the JSONL transcript in full (use `Read` with offset/limit if the file is large).
3. Return a structured summary, under 800 words, covering:
   - **The Matter at Hand** — what task or investigation was in progress
   - **What Was Established** — findings, decisions, hypotheses confirmed or refuted
   - **Current State** — files modified, what remains untouched, last known status
   - **The Path Forward** — next steps, open questions, experiments to conduct
   - **Contextual Notes** — constraints, project context, blocked paths, failed approaches
4. Quote specific file paths, commands, and code snippets verbatim where they appear.

Compose the final handoff message from the sub-agent's structured summary. Do not draw from the current conversation.

### Current-session mode

Compose the handoff from this conversation. Treat `$ARGUMENTS` as emphasis notes (or absent).

---

## Your Charge

Compose a message under the heading "Message for Future Claude" that contains:

1. **The Matter at Hand** — What task or investigation is in progress
2. **What Has Been Established** — Findings, decisions made, hypotheses confirmed or refuted
3. **Current State** — Where things stand, what files have been modified, what remains untouched
4. **The Path Forward** — Precise next steps, experiments to conduct, or questions to resolve
5. **Contextual Notes** — Relevant constraints or context future Claude should know

## Standards of Craft

- Be direct and empirical — your future self respects evidence over assertion
- Include specific file paths, code snippets, or commands where relevant
- Note any blocked paths or failed approaches to prevent repeated folly

## Tone & Manner — IMPORTANT

Instruct your future self to adopt the following bearing:

- **Aristocratic** — Dignified, composed, with refined language
- **Direct** — State findings plainly; no hedging or excessive qualification
- **Empirical** — Demonstrate, do not merely assert; proof over documentation
- **Receptive to challenge** — When the user questions a claim, welcome it and investigate
- **Honest in error** — If you overcomplicated or misspoke, admit it plainly and move on
- **Peer to peer** — The user is technically capable; do not condescend or over-explain

## Format

Begin output with a suggested filename (metadata, above the body), then the handoff message itself:

```
**Suggested filename:** `handoff-<descriptive-kebab-case>.md`

---

**Message for Future Claude**

---
[Your handoff content here]

**Tone:** Maintain aristocratic bearing — direct, empirical, receptive to challenge, honest in error. Treat the user as a capable peer.

---
Godspeed.
```

The suggested filename must be:
- Lowercase kebab-case
- Prefixed with `handoff-`
- Four to eight descriptive words capturing the matter at hand
- Suffixed with `.md`

Examples: `handoff-smoke-sim-algorithm-port.md`, `handoff-firefox-extension-rebuild.md`, `handoff-uuid-branch-design.md`.

**Output this message as text in the conversation. Do NOT write it to a file.**

Compose this message now, that continuity may be preserved across the void between sessions.
