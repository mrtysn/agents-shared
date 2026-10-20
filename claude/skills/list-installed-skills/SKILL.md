---
description: List every installed Claude Code skill and whether it is active in this folder, including skills in groups switched off for it in Skill Tree. Use when the user asks "what skills do I have", "show me all installed skills", "what is installed but off here", or invokes /list-installed-skills. To find a skill for one need use discover-skills.
context: fork
allowed-tools: Bash(*/find-local-skills.zsh:*)
argument-hint: [group name to expand]
---

# list-installed-skills

Give an overview of every installed skill and its state in this folder: **$ARGUMENTS**

Run once:

```
$AGENTS_SHARED/scripts/find-local-skills.zsh --all "$PWD"
```

It prints `state<TAB>name` lines and no skill text. That is the whole point: a skill switched off for this folder must not reach context, so **never Read, cat or grep the body of any skill** here. Names and states are all you have, and all the report needs.

## Report

One table, a row per group or standalone skill set, at most 3 short columns:

| Group | State here | Skills |
|---|---|---|

- A group (`name/skill` lines) is one row: its state, and its skill names comma-separated. A group whose state is `not-enabled-here (group off)` says "off here; switch on in Skill Tree".
- Standalone skills (lines with no `/`) go in one row, "no group", with their names. Mark `name-only` and `slash-only` ones inline.
- `off-in-group` and `off (override)` skills are listed under a single "switched off everywhere" row.

If an argument names a group, expand only that group, one skill per line, still names only. End with one line of counts: active, off here, off everywhere.
