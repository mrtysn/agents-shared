---
description: Start a new HTML page — a report, document, diagram wrapper or write-up — on the house style, with a sticky contents column on the left built from its section headings. Use whenever the user asks for an HTML page, report or visual output, so the left nav is there without being asked.
argument-hint: [title] [section headings…]
allowed-tools: Bash, Read, Write, Edit, Skill
---

# New HTML Page Skill

Every HTML page an agent writes starts from `project-lifecycle page-new`: the house head
(web-shared inlined, offline, light and dark, provenance stamp) plus a left contents column.
The user has asked for that column by hand many times; it is the default, not an extra.

Pages are local files (see the artifacts rule): never publish to Anthropic.

## Steps

1. **Pick the sections first.** The headings are the contents column, so decide them before
   scaffolding: two to eight, each a noun phrase (`Findings`, `Open questions`). No question
   to the user unless the content itself is undecided.
2. **Scaffold** into the repo or folder the page belongs in (notebook pages are
   `YYYY-MM-DD-slug.html`):

       project-lifecycle page-new --title "<two to four words>" --section "<Heading>" … \
         --repo <repo the page describes> --session <this session's id> --out <FILE>.html

   It prints the file's absolute path and refuses to overwrite. `--layout plain` only for a
   page with a single section or one that must be bare.
3. **Fill the sections.** Edit the file: replace each empty `<p></p>` with the content, in
   plain semantic HTML (headings, lists, `<table>` of three or four short columns,
   `<blockquote>`, `<code>`). No classes of your own; web-shared styles the elements. Add
   `<h3>` inside a section freely; the contents column lists only the `<h2>` sections.
4. **Look at it** before saying it is done: render at about 1300 and 600 px wide
   (`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new
   --screenshot=OUT.png --window-size=1300,900 file://FILE`, OUT in the scratchpad) and read
   the PNGs. The column sits left on wide, stacks on top when narrow.
5. **Hand over** the absolute path on its own line. Mention once that `notes-publish` can
   serve it, never run it unprompted.

## Pitfalls

- **Never write CSS for the page.** If the layout needs something web-shared lacks, add it to
  web-shared (`src/styles/components.css`), not to the page.
- **The column lists `<h2>` sections only**; a page whose headings are `<h3>` has no column.
- **Links are set up by the head**: every link except an in-page `#anchor` opens in a new tab
  with `rel="noopener noreferrer"`. Write plain `<a href>`; never add `target` yourself.
- A diagram (`/archify`) or a long data table is a section's content, not a reason to skip
  the scaffold.
