---
description: Search public Claude Code skill directories for an existing skill matching a need. Use when user asks "is there a skill for X", wants to find/discover skills, or before writing a new skill from scratch.
context: fork
allowed-tools: WebSearch, WebFetch, Read, Glob, Grep, Bash(gh search:*), Bash(gh api:*), Bash(ls:*)
argument-hint: <what the skill should do>
---

# discover-skills

Find existing skills across public skill directories for: **$ARGUMENTS**

If no arguments were given, return immediately asking for a description of what the skill should do — do not search on a guessed query.

## Check what is already installed first

Before touching the network:

```
ls -d ~/.claude/skills/*/ ./.claude/skills/*/ 2>/dev/null
grep -ril "<query>" ~/.claude/skills ~/.claude/plugins ./.claude/skills 2>/dev/null | head
```

Grep the descriptions, not just directory names — a skill that does the asked thing is
often named something else. If one already installed covers it, say so and stop.

## Sources

Query these in parallel. Directory sites are searchable by URL pattern; for the rest use WebSearch.

| Source | How to query |
|--------|--------------|
| claudemarketplaces.com | WebFetch `https://claudemarketplaces.com/search?q=<query>` — server-rendered; returns a match count then `<skill-name> <owner>/<repo> <description>` lines across skills, MCP servers and marketplaces. The most structured single source. Fallback WebSearch `site:claudemarketplaces.com <query>` |
| SkillsMP | WebFetch `https://skillsmp.com/search?q=<query>` — also server-rendered — fallback WebSearch `site:skillsmp.com <query>` |
| skills.sh (Vercel) | WebSearch `site:skills.sh <query>` (client-rendered — a direct fetch returns a ~600-char shell regardless of query) |
| claudeskills.info | WebSearch `site:claudeskills.info <query>` (client-rendered, ~48 chars) |
| awesome-claude-skills | Several repos share this name; WebSearch `awesome-claude-skills <query>` and check the top hits rather than assuming one canonical repo. Doubles as a plain web search, so it surfaces directories not listed here |
| GitHub topics | `gh search repos "<query>" --topic claude-skills --limit 10`, then again with `--topic agent-skills`. Highest-precision GitHub method — authors apply these deliberately |
| GitHub repos by keyword | `gh search repos "<query> claude skill" --limit 10` — the weakest source measured; returned zero for a query every other source answered well. Run it, but never conclude "nothing exists" from it |
| GitHub code | `gh search code --filename SKILL.md "<query>" --limit 10` — matches skill bodies, so precision varies with how common the term is |
| Plugin marketplaces | `gh search code --filename marketplace.json "<query>" --limit 10` — many skills ship inside plugins, declared in `.claude-plugin/marketplace.json`. Consistently the better of the two code searches |
| Hacker News | WebFetch `https://hn.algolia.com/api/v1/search?query=<query>+claude+skill&tags=story` — plain JSON, no key. Thin for common topics, decisive for niche ones, and the only source that carries *criticism*: open the comments on a high-point hit before recommending it. Use `tags=story`; the comment index is almost pure noise |
| anthropics/claude-plugins-official | `gh search code --repo anthropics/claude-plugins-official "<query>"`; catalog at `https://claude.com/plugins` |
| anthropics/claude-plugins-community | `gh search code --repo anthropics/claude-plugins-community "<query>"` — returned nothing usable on every probe; cheap to run, do not wait on it |
| anthropics/skills | `gh search code --repo anthropics/skills --filename SKILL.md "<query>"` (never pass an empty query — it silently returns nothing). Narrow by design: strong on document formats, empty on everything else |

Notes:
- `gh search code` is rate-limited to ~10 requests/minute. The code searches above are five of them; if they start returning empty, that is the limit, not the absence of results.
- WebSearch honours `site:` loosely — expect a Wikipedia result or two in every directory search. Ignore rather than report them.
- Sources deliberately **not** in this table, having been tested and failed: `npm search` (returns libraries like `pdf-parse`, never skills) and `claudeskills.cc` (a skill *generator* with a waitlist, not an index).
- Table order reflects measured yield on a three-query bake-off (`pdf`, `kubernetes`, `godot`), nothing else. Anthropic-published sources sit at the end because that is where their measured yield put them, and because this skill runs inside Anthropic tooling — listing them first would tilt results before any evidence is gathered. Three queries is a small and unrepresentative sample; treat the ordering as which source to read first when time is short, not as a verdict. Every candidate is judged by the criteria below, whoever published it.
- `--topic agent-skills` pulls large infrastructure repos that self-tagged (kubesphere, mirrord, dstack surfaced on a `kubernetes` probe). Star count is no help here — check that the repo actually ships a SKILL.md before treating it as a candidate.
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

A short table of the best matches (max 5): name, source repo link, one-line what-it-does, caveats.
Order it by how many independent sources surfaced the repo, then by stars, then by last
commit — all three are already in hand from the searches above. A skill that three
directories and a GitHub topic all returned is a stronger signal than one with more stars
found once.

Then a one-line recommendation: best candidate, or "nothing good exists — worth writing"
if that's the truth. Do not pad with weak matches.

End every report — always, even when everything ran and the answer is obvious — with a
coverage line: how many rows of the Sources table above you actually queried, out of the
number of rows it currently has, and the name of each one you did not.

```
Sources: 12/13 · skipped: anthropics/claude-plugins-community
Sources: 13/13
```

Count the table rows rather than trusting the number in this example — rows get added.
The local-installed check is not one of them.

This is unconditional on purpose. The earlier version fired only "if a source was skipped",
which requires noticing the condition before obeying it, and an observed run silently
skipped a source under exactly that wording. A line that is always present is one you can
check for. It matters most when the verdict is "nothing good exists" — a thin sweep of four
sources reads identically to a thorough thirteen unless the count says otherwise.

Do not install anything. If the user wants one installed, they'll say so. Three targets, by commitment:

- **Trial (default for a found skill):** `agents-shared/scripts/trial-skill.sh install <owner/repo> <path-in-repo>` — real directory in `~/.claude/skills/`, tracked by `.trial.json`, removable with `rm` or promotable with `promote` once it earns its keep.
- **Single session only:** no install — fetch the SKILL.md into scratchpad, read it, follow it.
- **Permanent from the start:** `agents-shared/claude/skills/<name>/` via the external-skill convention (`source.json` + `--establish-base`), only when the user says it's a keeper.

Read the full skill content from the source repo before installing by any route.
