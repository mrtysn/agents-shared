---
description: Craft a handoff message for a new session. Use when context must survive session boundaries. Pass a session UUID to consolidate a handoff from a past session instead of the current one.
argument-hint: [optional notes on scope/length, OR a session UUID]
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

1. Locate the transcript by globbing both roots, resolving `~` at runtime:
   - `~/.claude-personal/projects/*/<UUID>.jsonl`
   - `${CLAUDE_CONFIG_DIR:-~/.claude}/projects/*/<UUID>.jsonl`
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

Compose the handoff from this conversation.

`$ARGUMENTS`, when present, governs **scope and length** — not merely emphasis:

- "brief" / "short" / "quick" caps the body at ~200 words and licenses dropping any section that has nothing load-bearing to say.
- A named focus ("just the export work") excludes everything outside it.

---

## Your Charge

Compose a message under the heading "Message for Future Claude". **Default ceiling: 400 words.**

Draw on these sections, but include one only if omitting it would cost the next session real time. A handoff of three sections is a good handoff.

1. **The Matter at Hand** — What task or investigation is in progress
2. **What Has Been Established** — Findings, decisions made, hypotheses confirmed or refuted
3. **Current State** — Where things stand, what files have been modified, what remains untouched
4. **The Path Forward** — Precise next steps, experiments to conduct, or questions to resolve
5. **Contextual Notes** — Relevant constraints or context future Claude should know

## What Not to Carry

**Carry what is undecided, in motion, or a trap. Drop what is settled, cheap to re-derive, or enforced elsewhere.** The reasoning that produced a decision is not the decision.

Specifically, leave out:

- **Verified facts the next session can re-check in one command** — a config location, a binary path, a file count. Name where to look, not what you found.
- **Concluded side questions** — a licensing answer, a comparison already settled. If it changes nothing the next session does, it does not travel.
- **A ledger of your own errors** — what you initially got wrong is useless to a session that never made the mistake. Exception: a failed approach that would otherwise be re-attempted.
- **Instructions already in force** — style, tone, and process rules arrive via `CLAUDE.md` and `~/.claude/rules/` at startup. Restating them is duplication.
- **Warnings against re-litigating** — litigating a point nobody raised.

## Standards of Craft

- Be direct and empirical — your future self respects evidence over assertion
- Include specific file paths, code snippets, or commands where relevant
- Note any blocked paths or failed approaches to prevent repeated folly

## Format

Begin output with a suggested filename (metadata, above the body), then the handoff message itself:

```
**Suggested filename:** `handoff-<descriptive-kebab-case>.md`

---

**Message for Future Claude**

---
[Your handoff content here]

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
