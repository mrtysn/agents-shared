---
description: Search public sources for an existing prompt or instruction file for coding agents (CLAUDE.md, AGENTS.md, rules files, system prompts, slash-command prompts) matching a need. Use when user asks "is there a prompt for X", wants to find/discover prompts or instruction files, or before writing a new rule or CLAUDE.md section from scratch.
context: fork
allowed-tools: WebSearch, WebFetch, Read, Glob, Grep, Bash(gh search:*), Bash(gh api:*), Bash(ls:*)
argument-hint: <what the prompt should make the agent do>
---

# discover-prompts

Find existing prompts for coding agents across public sources for: **$ARGUMENTS**

"Prompt" here means instructions an agent loads: a `CLAUDE.md` / `AGENTS.md`, a rules
file (`.cursorrules`, `.claude/rules/*.md`), a system prompt, or a slash-command body.
General prompt libraries are searched too, for topics that are not about coding. Packaged
skills are `/discover-skills`.

If no arguments were given, return immediately asking for a description of what the
prompt should make the agent do — do not search on a guessed query.

## Check what is already installed first

Before touching the network:

```
ls ~/.claude/rules ~/.claude/commands ~/.claude/skills 2>/dev/null
grep -ril "<query>" ~/.claude/rules ~/.claude/commands ~/.claude/skills ./CLAUDE.md ./.claude 2>/dev/null | head
```

Grep the contents, not just filenames — a rule that covers the topic is often named
something else. If one already installed covers it, say so and stop. The rules in
`~/.claude/rules` load in every session, so a gap there is a real gap.

## Sources

Query these in parallel, but keep `gh search code` to the pace noted below. The two
prompt databases (prompts.chat, awesome-prompts lists) are the first place to look for a
topic that is not about coding: the GitHub code searches only find instruction files
that live inside real projects.

| Source | How to query |
|--------|--------------|
| GitHub code, CLAUDE.md | `gh search code --filename CLAUDE.md "<query>" --limit 10` — real project instructions in use; the best source for how people actually phrase a rule |
| GitHub code, AGENTS.md | `gh search code --filename AGENTS.md "<query>" --limit 10` — the cross-agent convention; same yield profile as CLAUDE.md |
| prompts.chat database | The largest open prompt collection (`f/prompts.chat`, formerly awesome-chatgpt-prompts). The site is client-rendered — a `?q=` URL returns the same page for any query — and `gh search code` over the repo does not index the data. Instead fetch the dataset once: `curl -sL https://raw.githubusercontent.com/f/prompts.chat/main/prompts.csv -o <scratchpad>/prompts.csv` (~6 MB), reuse the saved copy for every later query this session, and `grep -i "<query>"` it. General-purpose prompts, so judge fit for an agent before listing |
| awesome-prompts lists | `gh search repos "awesome prompts <query>" --limit 10` — curated collections such as `ai-boost/awesome-prompts`; read the list file and follow only the entries matching the query |
| Anthropic prompt library | WebSearch `site:docs.claude.com prompt-library <query>` — official example prompts for Claude; a fixed catalogue, so a miss is normal |
| GitHub repos by keyword | `gh search repos "<query> cursorrules"` and `gh search repos "<query> claude rules" --limit 10` — finds curated collections (e.g. awesome-cursorrules) whose per-topic files can be read directly |
| GitHub topics | `gh search repos "<query>" --topic system-prompts --limit 10`, then `--topic prompt-engineering` — repos of system prompts and prompt collections that self-tagged |
| Hacker News | WebFetch `https://hn.algolia.com/api/v1/search?query=<query>+claude+code+prompt&tags=story` — plain JSON, no key. Thin for common topics; the only source that carries *criticism*, so open the comments on a high-point hit before recommending it |
| Web | WebSearch `<query> CLAUDE.md example` and `<query> AGENTS.md rules` — catches blog posts that print the full prompt |

Notes:
- `gh search code` is rate-limited to ~10 requests/minute. Two code searches are listed; if they return empty, that is the limit, not the absence of results.
- Sources deliberately **not** in this table: `cursor.directory` (answered HTTP 429 on the first probe) and `promptbase.com` (HTTP 403) — a refusal ends requests to that host; `flowgpt`, `PromptHub` and `PromptDen` (accounts or client-rendered, no verified query URL); and Anthropic's published system-prompt page (a fixed document, not searchable by topic — fetch it directly only when the user asks about Claude's own system prompt).
- Every hit ultimately points at a GitHub repo or a page. Resolve to the source and judge the actual prompt text, not the listing. Collapse hits that resolve to the same file or repo; evaluate each once.

## Evaluating candidates

Fetch the actual prompt and check:

1. **Does it do the asked thing** — not merely adjacent keywords
2. **Portable** — flag instructions tied to one project's paths, stack, or private tooling; say what would have to be rewritten
3. **Safety** — read what it tells the agent to run; flag anything that executes remote code, phones home, disables permission checks, or asks the agent to hide actions from the user
4. **Conflict** — compare against the installed rules from the first step; flag any instruction that contradicts one
5. **Freshness** — last commit date on the source repo; prompts written for older models often carry workarounds that now hurt

## Output

A short table of the best matches (max 5): name, source link (to the file, not just the repo), one-line what-it-does, caveats.
Order it by how many independent sources surfaced it, then by stars, then by last commit.

Then a one-line recommendation: best candidate, or "nothing good exists — worth writing"
if that's the truth. Do not pad with weak matches.

End every report — always, even when everything ran and the answer is obvious — with a
coverage line: how many rows of the Sources table above you actually queried, out of the
number of rows it currently has, and the name of each one you did not.

```
Sources: 8/9 · skipped: Web
Sources: 9/9
```

Count the table rows rather than trusting the number in this example — rows get added.
The local-installed check is not one of them.

Do not install or save anything. A found prompt is reported, not written into
`~/.claude/rules` or any CLAUDE.md. If the user wants one adopted, they will say so; read
the full prompt from the source first, and adapt it rather than copying it verbatim.
