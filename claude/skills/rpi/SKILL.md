---
description: Research-Plan-Implement workflow. Deep codebase investigation, written plan with annotation cycles, then full execution.
argument-hint: [task description or requirements]
---

# Research-Plan-Implement

A three-phase workflow for non-trivial work. Each phase produces a written artifact that serves as shared mutable state between you and the user.

$ARGUMENTS

---

## Phase 1 — Research

Before any planning or implementation, investigate the codebase deeply.

1. **Explore thoroughly** — Read relevant files, trace code paths, understand architecture, find existing patterns and conventions. Go deep into the intricacies of how things work, not just surface-level structure.

2. **Write `research.md`** — Create a file in the project root containing your findings. This is not a verbal summary — it is a durable written artifact. Include:
   - Architecture and patterns discovered
   - Relevant code paths traced in detail
   - Existing conventions that must be followed
   - Dependencies and constraints identified
   - Specific file paths and code snippets as evidence

3. **Present for review** — Tell the user research.md is ready for review. Do not proceed to planning until they confirm.

**The research.md file is the review surface.** The user will read it to verify your comprehension before trusting you with a plan. If they find gaps, address them and update the document.

---

## Phase 2 — Planning

After research is approved, produce a detailed implementation plan.

1. **Write `plan.md`** — Create a file in the project root containing:
   - High-level approach and rationale
   - Specific files to create or modify, with code snippets showing actual changes
   - Trade-offs considered and decisions made
   - Edge cases and potential pitfalls
   - Dependencies and sequencing between changes

2. **Annotation cycle** — The user will open plan.md, add inline notes (comments, questions, corrections), and send it back. When they do:
   - Address every note in the document
   - Update the plan accordingly
   - Do not implement yet
   - Tell the user the updated plan is ready for another review

   Repeat this cycle until the user is satisfied. Expect 1-6 iterations.

3. **Add the task list** — Once the user approves the plan's direction, add a detailed implementation checklist to plan.md:
   - Organize by phases
   - Each phase contains specific, checkable tasks
   - Tasks reference exact files and changes from the plan
   - Use `- [ ]` checkbox format

4. **Get final approval** — Do not implement until the user explicitly says to proceed.

---

## Phase 3 — Implementation

Execute the plan completely and systematically.

1. **Follow the plan** — Implement every item, not a subset. Do not cherry-pick or skip tasks you consider minor.

2. **Mark progress** — As you complete each task, update plan.md to mark it done (`- [x]`). This gives the user a live view of progress.

3. **Code quality standards:**
   - No unnecessary comments or JSDoc that restates the obvious
   - Preserve strict typing — do not weaken types for convenience
   - Run typechecks and linting continuously as you work
   - Keep code clean of conversational artifacts

4. **If blocked** — Note the blocker in plan.md and continue with unblocked tasks. Do not stop entirely.

5. **Completion** — When all tasks are marked done, report to the user with a summary of what was implemented.

---

## Key Principles

- **Written artifacts over verbal summaries** — research.md and plan.md are the source of truth, not conversation messages
- **The user annotates, you update** — the markdown files are shared mutable state
- **No premature implementation** — phases are sequential gates, not suggestions
- **Thoroughness over speed** — this workflow exists for work that warrants careful treatment
