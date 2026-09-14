---
description: Find how shipped games handle a UI screen, element, flow, animation or visual style, and return a reference brief — shared patterns, notable variations, and 3–5 examples with deep links — recorded to a browsable ledger. Use when designing or restyling game UI, or when the user asks how other games do something, or wants UI references, examples or inspiration for a screen, HUD, popup, store, progression system, onboarding flow or accessibility setting.
context: fork
argument-hint: <screen, element, flow or style> [platform] [genre] [look] [fresh]
allowed-tools: Read, Write, Bash, WebFetch, WebSearch, ToolSearch, mcp__exa__web_fetch_exa, mcp__claude-in-chrome__*
---

# game-ui-refs

Find references for: **$ARGUMENTS**

If no arguments were given, return immediately asking what screen, element, flow or
style to look up — do not search on a guess.

Answer the question as asked. Do not read the current repository or fit the brief to a
project unless the request names one.

Every brief is kept in a ledger — the `game-ui-refs` repo, whose `scripts/record.py` is
its only writer:

```bash
REC="${DEV_ROOT:?run agents-shared/scripts/init-global.sh to set it}/game-ui-refs/scripts/record.py"
```

If that file does not exist, the ledger is not cloned on this machine: do the research
anyway, return the brief in the format of `record.py render`, and end with
`Not recorded — clone mrtysn/game-ui-refs into $DEV_ROOT to keep briefs.`

## 1. Check the ledger first

```bash
"$REC" find <the subject and platform words>
```

- A **100% match** answers the question already. Unless the request says `fresh` (or
  "again", "re-run", "update"), return `"$REC" render <id>` verbatim, followed by
  `Earlier brief from <date> — ask for a fresh run to browse again.` and stop.
- Weaker matches do not stop the run. Name them under **More to browse** as earlier
  briefs, by id.

## 2. Frame the question

Pull four things out of the request; leave any it does not state open rather than
inventing them.

| Part | Examples |
|---|---|
| Subject | level select · lives and refill timer · daily reward popup · pause menu · screen transition · subtitle options |
| Platform | mobile · PC/console · VR |
| Genre | casual/puzzle · match-3 · idle · RPG · roguelike |
| Look | pixel art · cosy pastel · a hex colour |

Then decide what kind of answer it wants — it picks the sources:

| Wants | Read first | Then |
|---|---|---|
| What a screen or element looks like | Game UI Database | Interface In Game |
| How it moves | Game UI Database with `vid=1` and a `Screen Transitions` / `Looping Animations` tag | 60fps.design |
| A multi-screen flow, paywall or store | Game UI Database | Paywall Screens, 60fps.design; flow libraries as links |
| Why games structure it that way | Deconstructor of Fun, Udonis, Game Developer | Game UI Database for the visuals |
| What it must include to be accessible | Game Accessibility Guidelines, Xbox guidelines, APX | Can I Play That? menu deep dives |

## 3. Build the URLs

Read `references/sites.md` (relative to this skill's base directory). Its **Access**
column is binding:

- `chrome` — view in a Chrome tab
- `fetch` — WebFetch, falling back to `mcp__exa__web_fetch_exa` (`urls` is an array)
- `links` — compose deep links for the brief; **never load the pages**

For Game UI Database, take every `scrn=`, `tag=` and `plat=` value from
`references/guidb-ids.md`. **Never guess an ID** — a wrong one silently shows a different
category. When no category fits — on any site — use the nearest parent or filter, or the
site's text search, and say which you used in the coverage note.

## 4. Read at human pace

This runs against small sites, one of them a free resource maintained by one person.

- **At most 12 navigations per request, across all sites.** A navigation is any URL
  load, including a filter checkbox that reloads the page. Scrolling is not one.
- **At most 25 screens opened in a site's viewer.** Open one only to read it closely or
  to get the link of an example you will cite.
- **Never page past the second page of a listing.** Game UI Database pages hold 50
  screens. Never sweep a category.
- **Never download, save or copy an image**, and never pass one to an image generator.
  View; describe in words; link.
- A login wall or paywall ends that site for this request. Never read through the user's
  signed-in session.

**Chrome.** Check the machine's focus policy first:

```bash
"${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/hooks/focus-policy.sh" --verdict
```

On `deny`, do not open Chrome — treat every `chrome` site as `links` and say so in
coverage. On `allow`:

1. Load the tools in one ToolSearch call: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__browser_batch,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__tabs_close_mcp`
2. Call `tabs_context_mcp` with `createIfEmpty: true` and work in the tab it returns.
   Call `tabs_create_mcp` only if a group already existed. Never touch the user's tabs.
3. Batch actions with `browser_batch` — it cuts the round trips several-fold.
4. The window may open small, showing one card per row, and resizing may not take.
   `scroll_to` each card rather than scrolling the page; it costs no navigation.
5. Read names and links from the page, never from pixels: `read_page` returns hrefs.
   `get_page_text` and `find` return text only.
6. Close the tab when done.

**Permalinks.**
- *Game UI Database* grid anchors point at the raw image, not a screen. Click the
  thumbnail; the tab URL gains `&autoload=<screen id>` — read it back with
  `tabs_context_mcp`. That listing URL plus `autoload` is the example's link.
- *Interface In Game* screens live at `/screenshots/<game-slug>-<caption-slug>/`.

If the extension is not connected or a tool errors twice, stop using Chrome, treat
`chrome` sites as `links`, and say so in coverage. Do not retry in a loop.

## 5. Record the brief

Cite only screens actually seen. A pattern needs at least three examples behind it;
fewer is a variation. In a pattern's `n of m`, **m is the number of screens viewed**.
Three to five examples. Every link is one you composed from the tables or read off a
page — never a URL reconstructed from memory.

Write the record as JSON (field reference: the ledger repo's `README.md`):

```json
{
  "query": "<$ARGUMENTS verbatim>",
  "subject": "<Subject>", "platform": "<or null>", "genre": null, "look": null,
  "patterns":   [{"text": "<placement, hierarchy, what is always visible…>", "n": 9, "m": 18}],
  "variations": [{"title": "<approach>", "text": "<what it does and what it buys; games named>"}],
  "examples":   [{"game": "<game>", "look_at": "<the one thing it shows best>", "url": "<link>"}],
  "more":       [{"url": "<filtered link or earlier brief>", "why": "<why it is worth a look>"}],
  "coverage": {
    "read":        [{"site": "<site>", "pages": 2, "note": "<filters used, fallbacks>"}],
    "links_only":  ["<site>"],
    "unavailable": [{"site": "<site>", "reason": "<why>"}]
  }
}
```

Then:

```bash
"$REC" add - <<'JSON'
{ …the record… }
JSON
```

`add` validates, commits, pushes and publishes to the viewer, printing one line per
step and the viewer link. A `record rejected` message lists what to fix — fix the JSON
and run `add` again. A failed push or publish leaves the record committed locally;
report the line, do not retry.

## 6. Return

Return `"$REC" render <id>` verbatim, then the status lines `add` printed (recorded,
pushed, published, viewer link). Nothing else — the render is the brief.

## Maintenance

- **Game UI Database adds a category** (its filter panel shows one `guidb-ids.md` lacks):
  run `scripts/guidb-ids.py > references/guidb-ids.md` from this skill directory. It reads
  the Wayback Machine's newest capture, not the live site.
- **A site changes its terms, dies or starts blocking**: fix its row in
  `references/sites.md`. Access follows the rule in that file's header, not convenience.
