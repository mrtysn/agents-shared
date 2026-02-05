---
description: Systematic refactoring with full cleanup. Use when extracting services, eliminating patterns, or cleaning up magic strings.
---

# Refactor Skill

When refactoring:

1. **Map scope first** — Find ALL instances of the pattern being refactored across `src/` and `tests/` before making any changes.

2. **Create a checklist** — List every affected file upfront. Track progress through each one.

3. **Same standards everywhere** — Apply identical standards to test files as production code. Magic strings, hardcoded values, and patterns being eliminated from `src/` must also be eliminated from `tests/`.

4. **Complete the cleanup** — No partial refactors. Don't stop mid-way through pattern elimination.

If the full cleanup cannot be completed in one session, explicitly state what remains.
