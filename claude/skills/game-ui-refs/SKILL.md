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

`find` lists every live brief, ordered by shared words. The order is only a hint: judge for
yourself which brief, if any, answers the request. One does when it covers the same subject
under any name ("stage select" is "level select"), and its platform, genre and look are the
same as asked or broader.

- A brief that answers the request answers it already. Unless the request says `fresh` (or
  "again", "re-run", "update"), return `"$REC" render <id>` verbatim, followed by
  `Earlier brief from <date> — ask for a fresh run to browse again.` and stop.
- On a fresh run over such a brief, set `"supersedes": "<that id>"` in the new record. The
  viewer then shows the new brief in its place.
- Briefs that are related but do not answer it do not stop the run. Name them under
  **More to browse** as earlier briefs, by id.

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

For Game UI Database, take every `scrn=`, `tag=` and `plat=` value from the lookup, never
from memory and never by reading `references/guidb-ids.md` whole (18 KB):

```bash
python3 "${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/claude/skills/game-ui-refs/scripts/guidb-ids.py" lookup level select
```

It prints the best-matching rows, rarest word first, then the other categories of the first
match's group, so a different name for the same screen still lands. **Never guess an ID** — a
wrong one silently shows a different category. When no category fits — on any site — use the
nearest parent or filter, or the site's text search, and say which you used in the coverage
note.

## 4. Read at human pace

This runs against small sites, one of them a free resource maintained by one person.

- **At most 12 navigations per request, across all sites.** A navigation is any URL
  load, including a filter checkbox that reloads the page. Scrolling is not one. A
  site's `pages` in coverage is its navigation count.
- **At most 25 screens opened in a site's viewer.** Open one only to read it closely or
  to get the link of an example you will cite.
- **At most 100 screens per brief**, across all sites — every screen recorded is one
  picture downloaded. Game UI Database listings arrive 50 at a time, sorted A–Z, so cutting
  one at the cap keeps only the games that start with early letters. Load the whole listing
  (scrolling is not a navigation), then pick the screens from it before looking at any:
  at most two per game, spread across the alphabet, at most 75 so a second source has room.
  The `pick` snippet below does it; say in coverage how many screens the listing held and how
  many games and screens were kept.
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
   Never touch the user's tabs.
3. Batch actions with `browser_batch` — it cuts the round trips several-fold.
4. The window may open small, showing one card per row, and resizing may not take.
   `scroll_to` each card rather than scrolling the page; it costs no navigation.
5. Read names and links from the page, never from pixels: `read_page` returns hrefs.
   `get_page_text` and `find` return text only.
6. Close the tab when done.

**Every screen you look at becomes a `screens` entry**, in viewing order — including
the ones you only saw in a grid. Pattern counts are derived from the screens' tags, so a
screen you looked at but did not record is a screen no pattern can count.

**Game UI Database — read the listing, don't click through it.** Every grid link carries
the screen's id, game and image. After the listing loads:

```js
const rows = [...document.querySelectorAll('a[data-imageid][href*="uploads/"]')].map((a) => {
  const d = document.createElement("div"); d.innerHTML = a.dataset.title || "";
  return [a.dataset.imageid, d.textContent.trim(), new URL(a.href).pathname].join("|");
});
window.__all = rows; rows.length
```

- Listings load 50 screens at a time. Scroll to the bottom and wait about 10 seconds for
  the next 50 — the URL gains `&scroll=<n>`, which is not a navigation. Stop at the page's
  "<n> SCREENS" total, or after 400 screens.
- Then pick at most two screens per game, spread across the listing, and cap the lot at 75.
  Game names have no `|`, and the rows keep the page's own order:

```js
const byGame = new Map();
for (const row of window.__all) {
  const game = row.split("|")[1];
  if (!byGame.has(game)) byGame.set(game, []);
  byGame.get(game).push(row);
}
let picked = [...byGame.values()].flatMap((g) => g.length > 2 ? [g[0], g[Math.floor(g.length / 2)]] : g);
if (picked.length > 75) picked = picked.filter((_, i) => Math.floor(i * 75 / picked.length) !== Math.floor((i - 1) * 75 / picked.length));
window.__rows = picked; `${window.__all.length} screens, ${byGame.size} games, ${picked.length} picked`
```

- Read the rows back in chunks: `window.__rows.slice(0, 12).join("\n")`, then the next
  12. A result over ~1,000 characters is cut off, and one containing HTML or a query
  string is blocked outright. Keep every row exactly as read: they go into the record
  as they are, and `record.py` builds each screen's `url` and `source` from them.
- **To look at the screens**, the grid is too small — three cards a row. Each link's
  `data-thumb` is a 500 px thumbnail: replace the page body with a grid of the thumbnails of
  the picked rows only (find each link by its `data-imageid`; 12 to a screen, each captioned
  with its row number in `window.__rows` and its game) and take a screenshot per screenful.
  The row number is the screen's index in the record. It loads nothing the grid had not already.
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

Cite only screens actually seen. While you look at the screens, note what each one does as
short tags (`left-rail`, `side-by-side`, `dimmed-backdrop`): the same word for the same
thing every time. `record.py` counts a pattern from the tags, so a count you did not tag is
a count nobody can check, and it never takes a number from you.

- A pattern is a `tag`: the screens carrying it show it. Add `"of": "<tag>"` when it only
  applies to some screens ("when leave and resume sit side by side, resume is on the right":
  `tag: resume-right`, `of: side-by-side`), so the denominator is the screens it applies to.
- A pattern needs at least three games behind it; fewer is a variation, and `add` rejects it.
- `why` on a pattern only when a source you read says why games do it. Never your own guess,
  and leave it out when no source did.
- Give a `note` (a few words) to every screen an example, variation or pattern points at.
- Three to five examples. Point each example, and each variation that has one, at its screen
  with `"screen": <index into screens>`. The index is the row number for a listing row.
- Every link is one you composed from the tables or read off a page — never a URL
  reconstructed from memory.

Write the record as JSON (field reference: the ledger repo's `README.md`). Game UI Database
screens go in as the `listing`: the rows you picked, copied as read, and the listing's URL.
Screens from other sites go in `screens` and follow the listing's. `tagged` maps each tag to
the screen indices carrying it, `"0,3,5-9"`:

```json
{
  "query": "<$ARGUMENTS verbatim>",
  "subject": "<Subject>", "platform": "<or null>", "genre": null, "look": null,
  "supersedes": null,
  "listing":    {"url": "<the listing page URL>", "rows": ["<id>|<game>|<path>", "…"]},
  "screens":    [{"game": "<game>", "site": "<site>", "url": "<the screen>", "source": "<its image URL>"}],
  "tagged":     {"<tag>": "0,3,5-9"},
  "notes":      {"4": "<what screen 4 shows, a few words>"},
  "patterns":   [{"text": "<placement, hierarchy, what is always visible…>", "tag": "<tag>", "of": "<tag, or omit>", "why": "<or omit>"}],
  "variations": [{"title": "<approach>", "text": "<what it does and what it buys; games named>", "screen": 4}],
  "examples":   [{"game": "<game>", "look_at": "<the one thing it shows best>", "url": "<link>", "screen": 0}],
  "more":       [{"url": "<filtered link or earlier brief>", "why": "<why it is worth a look>"}],
  "coverage": {
    "read":        [{"site": "<site>", "pages": 1, "note": "<filters used, fallbacks, the listing's size and how many screens were kept>"}],
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

`add` expands the listing, derives every pattern's counts, saves the pictures, commits, pushes
and publishes to the viewer, printing one line per step and the viewer link. A picture that
fails to download is reported and skipped; the brief is kept. A `record rejected` message lists
what to fix — fix the JSON and run `add` again. If git refuses the commit, `add` removes the
ledger line and pictures it wrote, so running it again is safe. A failed push or publish leaves
the record committed locally; report the line, do not retry.

## 6. Return

Return `"$REC" render <id>` verbatim, then the status lines `add` printed (pictures
saved, recorded, pushed, published, viewer link). Nothing else — the render is the
brief, and the pictures are in the viewer.

## Maintenance

- **Game UI Database adds a category** (its filter panel shows one `guidb-ids.md` lacks):
  run `scripts/guidb-ids.py > references/guidb-ids.md` from this skill directory. It reads
  the Wayback Machine's newest capture, not the live site. `scripts/guidb-ids.py lookup <words>`
  searches that table; it is how a run reads it.
- **A site changes its terms, dies or starts blocking**: fix its row in
  `references/sites.md`. Access follows the rule in that file's header, not convenience.
