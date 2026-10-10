---
description: Start a new HTML page — a report, document, diagram wrapper or write-up — on the house style, with a sticky contents column on the left built from its section headings. Use whenever the user asks for an HTML page, report or visual output, so the left nav is there without being asked. Also the decision form — questions put to the user on a page, with screenshots and long context, answered back to the agent — for decisions AskUserQuestion would show badly.
argument-hint: [title] [section headings…]
allowed-tools: Bash, Read, Write, Edit, Skill
---

# New HTML Page Skill

Every HTML page an agent writes starts from `project-lifecycle page-new`: the house head
(web-shared inlined, offline, light and dark, provenance stamp) plus a left contents column.
The user has asked for that column by hand many times; it is the default, not an extra.

Pages are local files (see the artifacts rule): never publish to Anthropic.

## Steps

1. **Pick the mode from the content.** What the page presents decides its shape:

   | Mode | When the content is |
   |---|---|
   | `report` | findings, a write-up (default) |
   | `decision-brief` | a recommendation among options: verdict first |
   | `dashboard` | numbers: headline figures, a breakdown, a table |
   | `guide` | a procedure: steps in order, with pictures |
   | `card-board` | items grouped by category or interval |
   | `schedule` | events by day, filterable by track |
   | `gallery` | images or videos to browse |
   | `status-board` | where work stands: waiting, active, done, blocked |
   | `link-collection` | links worth keeping, grouped |
   | `status-grid` | where things are and how many copies or owners each has |
   | `tool` | a calculator: inputs, live results |

   Each mode has default sections; give `--section` to name your own (`schedule` and
   `link-collection` always need them: the days, the groups).
2. **Pick the sections.** The headings are the contents column: two to eight, each a noun
   phrase. No question to the user unless the content itself is undecided.
3. **Scaffold** into the repo or folder the page belongs in (notebook pages are
   `YYYY-MM-DD-slug.html`):

       project-lifecycle page-new --mode <mode> --title "<two to four words>" [--section "<Heading>" …] \
         [--palette warm|pastel|slate|FILE] --repo <repo> --session <this session's id> --out <FILE>.html

   It prints the file's absolute path and refuses to overwrite. Two or more sections get the
   contents column, one section is plain. `--palette` recolours: web-shared's `warm` (cream,
   violet), `pastel` (peach, rounded type), `slate` (neutral, system type), or a file of custom
   properties; a repo's own `page-palette.css` is used without asking. No palette is the house
   style, and the right default.
4. **Fill the sections.** Edit the file. The scaffold's markup names web-shared's classes and
   its HTML comments say how to fill them: replace each placeholder, repeat the item markup
   (a card, an event, a status row) as often as needed. Outside those, plain semantic HTML
   (headings, lists, `<table>` of three or four short columns, `<blockquote>`, `<code>`). Any
   page may use any mode's components (`ws-callout`, `ws-facts`, `ws-stats--tiles`, tags with
   `data-tone="1"`…`"6"`); README of web-shared and `components.css` list them. Add `<h3>`
   inside a section freely; the contents column lists only the `<h2>` sections.
5. **Look at it** before saying it is done: render at about 1300 and 600 px wide
   (`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new
   --screenshot=OUT.png --window-size=1300,900 file://FILE`, OUT in the scratchpad) and read
   the PNGs. The column sits left on wide, stacks on top when narrow.
6. **Hand over** the absolute path on its own line. Mention once that `notes-publish` can
   serve it, never run it unprompted.

## Decision form: asking the user on a page

When a decision turns on something seen, or on more context than a terminal prompt holds
(see the asking-for-decisions rule), the questions go on a page instead of AskUserQuestion.

1. **Write the spec** as JSON where the form goes (the repo the decision is about, or the
   notebook; never the scratchpad): per question an `id`, a `heading`, `context_html` with the
   facts the choice turns on, `images` (`src` relative to the form, `caption`), and `options`
   (`id`, `label`, `consequence`, `recommended` on one). `multi`, `allow_other` and `skippable`
   default to false, true, true. Full format: `project_lifecycle/decision.py`. Screenshots go
   in the same folder.
2. **Scaffold**:

       project-lifecycle page-new --mode decision-form --spec <SPEC>.json --title "<what is decided>" \
         --repo <repo> --session <this session's id> --out <FORM>.html

3. **Wait** with a background Bash command (`run_in_background: true`), never in the foreground:

       project-lifecycle decision-wait <FORM>.html --json

   It opens the form in the browser without taking focus and exits when the user submits. Tell
   the user the form is open, with its absolute path on its own line, and stop.
4. **On the completion notice**, read the answers from its output or `<FORM>.answers.json`:
   `{"choice": id}`, `{"choices": [ids]}` when several may be picked, `"other"` with `text` for
   free text, `text` beside a pick as a note, `{"skipped": true}`, `{"choice": null}` when
   unanswered. Act on them as on AskUserQuestion answers.

A rerun prints answers already given; `--revise` reopens the form with them filled in. If the
user pastes JSON from a form opened from disk, write it to `<FORM>.answers.json` yourself.

## Pitfalls

- **Never write CSS or script for the page.** If the layout needs something web-shared lacks, add
  it to web-shared (`src/styles/components.css`) in the standalone clone that the
  `web_shared_root` setting names, never in a site's submodule, and not to the page. The scripts page-new emits
  itself (theme, links, contents highlight, filters, the decision form's) are part of the tool.
  The one exception is the `tool` mode's script block, which holds the page's calculation.
- **A value shown as data rides in a custom property** (`style="--value: 42%"` on a `.ws-bar`),
  never a style rule.
- **No `<aside>` in the main column**: classless.css floats it into the margin as a sidenote.
  Use `<div class="ws-callout">`.
- **The column lists `<h2>` sections only**; a page whose headings are `<h3>` has no column.
- **Links are set up by the head**: every link except an in-page `#anchor` opens in a new tab
  with `rel="noopener noreferrer"`. Write plain `<a href>`; never add `target` yourself.
- A diagram (`/archify`) or a long data table is a section's content, not a reason to skip
  the scaffold.
