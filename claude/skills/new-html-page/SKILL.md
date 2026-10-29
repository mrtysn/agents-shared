---
description: Start a new HTML page — a report, document, diagram wrapper or write-up — on the house style, with a sticky contents column on the left built from its section headings. Use whenever the agent writes anything for the user to read (a report, survey, comparison, plan or write-up), whenever the user asks for an HTML page or visual output, for slides, a deck or a presentation (deck mode), and to turn a skill's Markdown report into a page (--from-markdown). Also the decision form — questions put to the user on a page, with screenshots and long context, answered back to the agent — for decisions AskUserQuestion would show badly.
argument-hint: [title] [section headings…]
allowed-tools: Bash, Read, Write, Edit, Skill
---

# New HTML Page Skill

Every HTML page an agent writes starts from `project-lifecycle page-new`: the house head
(links the repo's `ws/` folder filled from web-shared, offline, light and dark, provenance stamp) plus a left contents column.
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
   | `deck` | a talk to present: one slide per section, speaker notes, keyboard and touch |
   | `progress` | long work to watch live: a transfer, a copy, a render; see "Progress page" below |

   Each mode has default sections; give `--section` to name your own (`schedule`,
   `link-collection` and `deck` always need them: the days, the groups, the slides).
   A deck is the one mode with no contents column. The title becomes the first slide, each
   `--section` is a slide holding one point, and the `.ws-notes` div on a slide is what the
   presenter says (`N` shows it; printing leaves it out). Pass no `--layout`. Give a slide its
   composition with `--section "Heading::layout"`: `stat` (one big number), `split` (two columns),
   `art` (text beside a picture), `figure`, `quote`, or `list` (default); vary them, a deck of lists
   reads flat. `+accent` or `+soft` after the layout sets the slide's ground, and the `ws-kicker`
   line above each title takes a two-word label. **Turning an existing report into a deck:** read the
   whole report first, including its later sections, because a follow-up section ("Result", "Decisions")
   can overturn the first half; order slides so evidence comes before the claim that depends on it; give each
   split column one point; a one-sentence finding is a line on a slide, not a stat slide; the dropped tables
   stay in the report, which the deck accompanies. Have a fresh agent audit the deck against the report
   before handing it over. A decision form or a reference page with no argument to rank is a poor deck
   source: the deck keeps the decisions and loses the risks and triggers, so give it a one-page record instead.
2. **Pick the sections.** The headings are the contents column: two to eight, each a noun
   phrase. No question to the user unless the content itself is undecided.
3. **Scaffold** into the repo or folder the page belongs in (notebook pages are
   `YYYY-MM-DD-slug.html`):

       project-lifecycle page-new --mode <mode> --title "<two to four words>" [--section "<Heading>" …] \
         [--palette warm|pastel|slate|FILE] --repo <repo> --session <this session's id> --out <FILE>.html

   From a Markdown report (one a skill wrote, or your own draft), skip choosing sections:
   `page-new --from-markdown <FILE>.md --mode <mode> … --out <FILE>.html` takes the title from
   its `#` heading and the sections from its `##` headings; then finish it as in step 4 with
   the mode's components (a verdict callout, tiles, tags) that Markdown has no syntax for.

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
   the PNGs. The column sits left on wide, stacks on top when narrow. Headless Chrome clamps
   `--window-size` to 500 px wide, so a "320 px" screenshot is a 500 px layout cropped: text
   cut at the right edge there is the crop, not an overflow. A real 320 px check needs a
   browser window resized to 320 (claude-in-chrome's `resize_window` on a local server).
6. **Hand over** the absolute path on its own line. Mention once that `notes-publish` can
   serve it, never run it unprompted.

## Progress page: long work shown live

When the user will wait on long work (a copy to a drive, an adb push, an rsync to a server, a
render), give them a page that moves instead of answering "what's the progress" by hand.

1. **Scaffold** in a folder of its own (the repo the work belongs to, or a dated notebook
   folder; never the scratchpad): `page-new --mode progress --title "<what moves>" --out <DIR>/<NAME>.html`.
   Write the Notes section: what moves, from where to where, what happens after.
2. **Report** with `project-lifecycle progress-write <DIR>/<NAME>.progress.json --item ID --label …`:
   - `--done N --total N` from a loop, in any `--unit` (bytes, seconds, files, steps).
   - `--watch PATH --total N` for a local cp or ditto whose destination grows; the server reads
     its size. Not rsync without `--inplace`, not adb (the file grows on the device).
   - `--from rsync|ffmpeg|lines` with the worker piped in: `rsync --info=progress2` (3.1+, so
     Homebrew's or the server's, not macOS's openrsync), `ffmpeg -progress pipe:1` with
     `--total` as the input's seconds, or plain `done [total]` lines. A job on another machine
     pipes through its ssh session: `ssh host rsync --info=progress2 … | progress-write --from rsync …`.
   No total known yet: leave it out. `--state failed` on a failure, `--note` for one line under
   the bar. A step that is silent for minutes by design gets `--stall-after`/`--stale-after`.
3. **Serve** with `project-lifecycle progress-serve <DIR>/<NAME>.html --until-finished` as a
   background command. It opens the page without taking focus and exits 0 when every item is
   done, 1 when one failed, 2 on `--timeout`. Give the user the `http://127.0.0.1:<port>/` address its first
   line prints, not the HTML file's path: the page moves only while it is served, and from disk it stays still.

## Decision form: asking the user on a page

When a decision turns on something seen, or on more context than a terminal prompt holds
(see the asking-for-decisions rule), the questions go on a page instead of AskUserQuestion.

1. **Write the spec** as JSON where the form goes (the repo the decision is about, or the
   notebook; never the scratchpad): per question an `id`, a `heading`, `context_html` with the
   facts the choice turns on, `images` (`src` relative to the form, `caption`), and `options`
   (`id`, `label`, `consequence`, `recommended` on one). **Set `multi` on every question**; the
   scaffold refuses a question with options and no `multi`. `true` for options that can be
   combined (several features to keep, a "both" answer would make sense), `false` only when
   exactly one must win (a font, one layout). When unsure, ask whether the user could want two:
   if yes, `true`. A long list the user prunes (items scored keep, to untick) gets `"checked": true`
   on each option that starts ticked; a "Recommended" badge alone leaves the box empty.
   `allow_other` and `skippable` default to true. Full format: `project_lifecycle/decision.py`. Screenshots go
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
- **A table whose cells hold sentences needs `<table class="ws-table--wrap">`.** A plain
  `<table>` is styled as data: every cell `nowrap` and right-aligned, so prose cells run off
  the column and scroll. Use the plain one only for short values and numbers.
- **The column lists `<h2>` sections only**; a page whose headings are `<h3>` has no column.
- **Links are set up by the head**: every link except an in-page `#anchor` opens in a new tab
  with `rel="noopener noreferrer"`. Write plain `<a href>`; never add `target` yourself.
- **No runtime third-party hosts (map tiles, APIs), and test from `file://`, with every fetched image
  viewed**: see the artifacts rule.
- A diagram (`/archify`) or a long data table is a section's content, not a reason to skip
  the scaffold.
