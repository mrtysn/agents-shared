# Artifacts

**Never publish an Artifact.** The Artifact tool uploads content to Anthropic's (claude.ai) servers, which leaks private machine contents off-machine — unacceptable even though artifacts are private-by-default.

- When asked for "an HTML", a report, or any visual output, write a **local HTML file** on disk with the Write tool and give the file path.
- Make it self-contained: inline all CSS/JS, no CDNs, works offline.
- Do not offer to publish or share through Anthropic.

## Every page starts from `page-new`

A page an agent writes (a report in the notebook, a diagram, a document for notes-shared)
starts from the `/new-html-page` skill, never from CSS written for the occasion:

    project-lifecycle page-new --title "<two to four words>" --section "<Heading>" … --repo <the repo it describes> --session <this session's id> --out FILE.html

It writes a complete page: web-shared's stylesheets inlined with their network imports
dropped (one file, reads offline), light and dark from the reader's preference, a
`provenance` meta tag (repo and revision described, session, date), and **a sticky contents
column on the left built from the section headings**: the user wants it on every report and
has asked for it by hand each time it was missing. The sections are plain semantic HTML:
headings, paragraphs, lists, `<table>`, `<blockquote>`, `<code>`. No classes of your own;
web-shared styles the elements. Keep tables to three or four short columns, wider ones
scroll. `--layout plain` is for a page with a single section. `project-lifecycle page-head`
alone prints just the `<head>` for a page that must be laid out by hand.

## Publishing is a separate, deliberate step

A page is local by default. When it is meant for someone else, it goes out with
`notes-publish FILE.html` (private until an audience is set with `--audience`), which
serves it on the notes site behind the portal. Say in one line that the page can be
published that way; never publish on your own initiative.
