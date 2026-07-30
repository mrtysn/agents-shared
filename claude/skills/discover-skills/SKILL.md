---
description: Search public Claude Code skill directories for an existing skill matching a need. Use when user asks "is there a skill for X", wants to find/discover skills, or before writing a new skill from scratch.
context: fork
allowed-tools: WebSearch, WebFetch, Read, Bash(gh search:*), Bash(gh api:*)
argument-hint: <what the skill should do>
---

# discover-skills

Find existing skills across public skill directories for: **$ARGUMENTS**

If no arguments were given, return immediately asking for a description of what the skill should do — do not search on a guessed query.

## Sources

Query these in parallel. Directory sites are searchable by URL pattern; for the rest use WebSearch.

| Source | How to query |
|--------|--------------|
| skills.sh (Vercel) | WebSearch `site:skills.sh <query>` (the site's own search is client-rendered — WebFetch reads an empty shell) |
| SkillsMP | WebFetch `https://skillsmp.com/search?q=<query>` — fallback WebSearch `site:skillsmp.com <query>` |
| claudemarketplaces.com | WebSearch `site:claudemarketplaces.com <query>` |
| claudeskills.info | WebSearch `site:claudeskills.info <query>` |
| awesome-claude-skills | Several repos share this name; WebSearch `awesome-claude-skills <query>` and check the top hits rather than assuming one canonical repo |
| GitHub at large | `gh search repos "<query> claude skill" --limit 10` and `gh search code --filename SKILL.md "<query>" --limit 10` |
| Plugin marketplaces | `gh search code --filename marketplace.json "<query>" --limit 10` — many skills ship inside plugins; marketplace repos declare them in `.claude-plugin/marketplace.json` |
| anthropics/claude-plugins-official | `gh search code --repo anthropics/claude-plugins-official "<query>"`; catalog at `https://claude.com/plugins` |
| anthropics/claude-plugins-community | `gh search code --repo anthropics/claude-plugins-community "<query>"` |
| anthropics/skills | `gh search code --repo anthropics/skills --filename SKILL.md "<query>"` (never pass an empty query — it silently returns nothing) |

Notes:
- Table order is not a ranking. Anthropic-published sources sit at the end precisely so their position does not imply precedence — this skill runs inside Anthropic tooling, and listing them first would tilt results before any evidence is gathered. Every candidate is judged by the criteria below, whoever published it.
- Publisher is not evidence of quality or safety. Anthropic states it does not control what a plugin contains and cannot verify that it works as intended, so appearing in an official or screened marketplace does not substitute for reading the skill.
- SkillsMP, claudemarketplaces, and claudeskills.info are automated GitHub scrapes, so the same skill surfaces repeatedly across them — relevant to dedup, not to quality.
- Every directory entry ultimately points at a GitHub repo. Resolve to the source repo and judge the actual SKILL.md, not the directory listing. SKILL.md is often nested (`skills/<name>/`, `.claude/skills/`, `src/skills/`); find it with `gh api repos/<owner>/<repo>/git/trees/HEAD?recursive=1 --jq '.tree[].path' | grep -i skill`.

## Evaluating candidates

First resolve every hit to its source GitHub repo and collapse candidates that resolve to the same repo — the directories scrape the same pool, so one skill often surfaces as several hits. Evaluate each repo once.

For each remaining candidate, fetch the actual SKILL.md and check:

1. **Does it do the asked thing** — not merely adjacent keywords
2. **Self-contained** — flag skills that depend on external scripts, API keys, or MCP servers
3. **Safety** — read what its instructions tell the agent to run; flag anything that executes remote code, phones home, or has overly broad allowed-tools
4. **Freshness** — last commit date on the source repo

## Output

A short table of the best matches (max 5): name, source repo link, one-line what-it-does, caveats. Then a one-line recommendation: best candidate, or "nothing good exists — worth writing" if that's the truth. Do not pad with weak matches.

Do not install anything. If the user wants one installed, they'll say so; installation target is `~/.claude/skills/<name>/` (personal) or `agents-shared/claude/skills/<name>/` (shared), copied from the source repo after reading the full skill content.
