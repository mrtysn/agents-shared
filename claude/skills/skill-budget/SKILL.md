---
description: Audit Claude Code skills against the system-prompt skill listing budget. Use when the doctor warns about truncated skill descriptions, or to see which skills consume the most budget and whether any exceed the 1,536-char per-skill cap.
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [--top 10, --over-cap, --source user|project|plugin, --kind skill|command, --context 200000, --budget-fraction 0.02, --json]
---

# skill-budget

Meta-analysis of installed Claude Code skills and slash-commands. Reports description size per skill against:

- **Per-skill cap**: 1,536 chars (description + when_to_use), enforced by the harness — any single skill larger than this gets truncated regardless of total budget.
- **Total budget**: `skillListingBudgetFraction` (default 1% of context). When total exceeds budget, descriptions of least-used skills are dropped from the system prompt.

Run the script:

```bash
python3 ~/dev/personal/agents-shared/scripts/skill-budget.py $ARGUMENTS
```

**Flags:**

- `--top N` / `-n N`: limit to top N rows by total chars
- `--over-cap`: only show skills exceeding the 1,536-char per-skill cap
- `--source user|project|plugin`: filter by where the skill lives
- `--kind skill|command`: filter by `SKILL.md` skills vs single-file `commands/*.md`
- `--context N` / `-c N`: context window in tokens (default: 1,000,000)
- `--budget-fraction F` / `-b F`: budget fraction (default: 0.01)
- `--json`: emit JSON for further processing

**Discovery scope:**

- `~/.claude/skills/*/SKILL.md` and `~/.claude/commands/*.md` (user)
- `<cwd>/.claude/skills/*/SKILL.md` and `<cwd>/.claude/commands/*.md` (project; symlinks resolved and deduped)
- `~/.claude/plugins/**/skills/*/SKILL.md` (plugin)

**Not measured (bundled in the Claude Code binary):**
`init`, `review`, `security-review`, `claude-api`, `update-config`, `keybindings-help`, `simplify`, `fewer-permission-prompts`, `loop`, `schedule`. The script lists these explicitly so the gap between on-disk total and the doctor-reported size is intelligible.

**Typical flows:**

- "Why was the listing truncated?" → `skill-budget --top 15`
- "Anything blowing the per-skill cap?" → `skill-budget --over-cap`
- "What does my project add on top of user-level?" → `skill-budget --source project`
- "Audit at the smaller default context" → `skill-budget --context 200000`

Present the table to the user directly. Do not propose edits to skill files unless asked.
