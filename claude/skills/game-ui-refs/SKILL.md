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
- On a fresh run over a match, set `"supersedes": "<that id>"` in the new record. The
  viewer then shows the new brief in its place.
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
| How it moves | Game UI Database with a `Screen Transitions` / `Looping Animations` tag | 60fps.design, easings.net for curve names |
| A multi-screen flow, paywall or store | Game UI Database | Paywall Screens, 60fps.design; flow libraries as links |
| Why games structure it that way | Deconstructor of Fun, Udonis, Game Developer | Game UI Database for the visuals |
| What it must include to be accessible | Game Accessibility Guidelines, Xbox guidelines, APX | Can I Play That? menu deep dives |
| Which games ship a given accessibility feature | Gaming Accessibility Database | Game Accessibility Nexus |
| Platform rules — touch targets, text sizes, safe areas | Apple HIG (designing for games), Xbox guidelines | Game UI Database for how games meet them |
| Loading screens | Video Game Loading Interface Archive | Game UI Database `Loading Screen` |
| A mechanic's name, or how a system usually works | Gameplay Design Patterns wiki | Game UI Database for its screens |
| A stylised, cinematic or diegetic look | HUDS+GUIS | Game UI Database with a `UI Style` or `Elements` tag |
| Economy or pricing behind a store or offer | Game Economist Consulting, Deconstructor of Fun | Game UI Database `Monetisation` screens |

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
- **Never download or save an image yourself**, and never pass one to an image
  generator. Record each screen's image URL as `source`; `record.py` fetches every one
  exactly once, a second apart, into the private ledger.
- A login wall or paywall ends that site for this request. Never read through the user's
  signed-in session.

**Chrome.** Check the machine's focus policy first:

```bash
"${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/hooks/focus-policy.sh" --verdict
```

On `deny`, do not open Chrome — treat every `chrome` site as `links` and say so in
coverage. On `allow`:

1. Load the tools in one ToolSearch call: `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__browser_batch,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__tabs_close_mcp`
2. Call `tabs_context_mcp` with `createIfEmpty: true` and work in the tab it returns.
   Call `tabs_create_mcp` only if a group already existed. Never touch the user's tabs.
3. Batch actions with `browser_batch` — it cuts the round trips several-fold.
4. The window may open small, showing one card per row, and resizing may not take.
   `scroll_to` each card rather than scrolling the page; it costs no navigation.
5. Read names and links from the page, never from pixels: `read_page` returns hrefs.
   `get_page_text` and `find` return text only.
6. Close the tab when done.

**Every screen you look at becomes a `screens` entry**, in viewing order — including
the ones you only saw in a grid. `record.py` rejects a brief whose pattern totals (`m`)
differ from the number of screens recorded.

**Game UI Database — read the listing, don't click through it.** Every grid link carries
the screen's id, game and image. After the listing loads:

```js
const rows = [...document.querySelectorAll('a[data-imageid][href*="uploads/"]')].map((a) => {
  const d = document.createElement("div"); d.innerHTML = a.dataset.title || "";
  return [a.dataset.imageid, d.textContent.trim(), new URL(a.href).pathname].join("|");
});
window.__rows = rows; rows.length
```

- Listings load 50 screens at a time. Scroll to the bottom and wait a few seconds to load
  the rest — the URL gains `&scroll=<n>`, which is not a navigation. The page's
  "<n> SCREENS" count says when all have arrived.
- Read the rows back in chunks: `window.__rows.slice(0, 12).join("\n")`, then the next
  12. A result over ~1,000 characters is cut off, and one containing HTML or a query
  string is blocked outright.
- Each row gives `url` = the listing URL plus `&autoload=<id>`, and `source` =
  `https://www.gameuidatabase.com<path>`.
- A `/uploads/video/….mp4` path is a video. The site refuses direct downloads of video
  files, so record that screen without `source` and link it.

**Interface In Game.** `url` is `/screenshots/<game-slug>-<caption-slug>/`; `source` is the
`wp-content/uploads/<game>/<slug>.png` image on that screen's card, from `read_page`.

Take every value from the page, never from pixels. When a page exposes no image URL,
record the screen without `source` — it keeps its place in the count, just without a
picture.

If the extension is not connected or a tool errors twice, stop using Chrome, treat
`chrome` sites as `links`, and say so in coverage. Do not retry in a loop.

## 5. Record the brief

Cite only screens actually seen. A pattern needs at least three examples behind it;
fewer is a variation. In a pattern's `n of m`, **m is the number of screens viewed** —
the length of `screens`. Three to five examples. Point each example, and each variation
that has one, at its screen with `"screen": <index into screens>`. Every link is one you composed from the tables or read off a
page — never a URL reconstructed from memory.

Write the record as JSON (field reference: the ledger repo's `README.md`):

```json
{
  "query": "<$ARGUMENTS verbatim>",
  "subject": "<Subject>", "platform": "<or null>", "genre": null, "look": null,
  "supersedes": null,
  "screens":    [{"game": "<game>", "site": "<site>", "url": "<the screen>", "source": "<its image URL>", "note": "<what it shows, a few words>"}],
  "patterns":   [{"text": "<placement, hierarchy, what is always visible…>", "n": 9, "m": 18}],
  "variations": [{"title": "<approach>", "text": "<what it does and what it buys; games named>", "screen": 4}],
  "examples":   [{"game": "<game>", "look_at": "<the one thing it shows best>", "url": "<link>", "screen": 0}],
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

`add` validates, saves the pictures, commits, pushes and publishes to the viewer,
printing one line per step and the viewer link. A picture that fails to download is
reported and skipped; the brief is kept. A `record rejected` message lists what to fix — fix the JSON
and run `add` again. A failed push or publish leaves the record committed locally;
report the line, do not retry.

## 6. Return

Return `"$REC" render <id>` verbatim, then the status lines `add` printed (pictures
saved, recorded, pushed, published, viewer link). Nothing else — the render is the
brief, and the pictures are in the viewer.

## Maintenance

- **Game UI Database adds a category** (its filter panel shows one `guidb-ids.md` lacks):
  run `scripts/guidb-ids.py > references/guidb-ids.md` from this skill directory. It reads
  the Wayback Machine's newest capture, not the live site.
- **A site changes its terms, dies or starts blocking**: fix its row in
  `references/sites.md`. Access follows the rule in that file's header, not convenience.
