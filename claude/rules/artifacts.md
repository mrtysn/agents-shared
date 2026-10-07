# Artifacts

**Never publish an Artifact.** The Artifact tool uploads content to Anthropic's (claude.ai) servers, which leaks private machine contents off-machine — unacceptable even though artifacts are private-by-default.

- When asked for "an HTML", a report, or any visual output, write a **local HTML file** on disk with the Write tool and give the file path.
- Make it self-contained: inline all CSS/JS, no CDNs, works offline.
- Do not offer to publish or share through Anthropic.

## Every page starts from the house head

A page an agent writes (a report in the notebook, a diagram, a document for notes-shared)
starts from `project-lifecycle page-head`, never from CSS written for the occasion:

    project-lifecycle page-head --title "<two to four words>" --repo <the repo it describes> --session <this session's id> > head.html

It prints a complete `<head>`: web-shared's stylesheets inlined with their network imports
dropped (one file, reads offline), light and dark from the reader's preference, and a
`provenance` meta tag with the repo and revision described, the session and the date. The
page is `<!DOCTYPE html><html lang="en">` + that head + a `<body><main>…</main></body>` in
plain semantic HTML: headings, paragraphs, lists, `<section>`, `<blockquote>`, `<table>`,
`<code>`. No classes of your own; web-shared styles the elements. Keep tables to three or
four short columns, wider ones scroll.

## Publishing is a separate, deliberate step

A page is local by default. When it is meant for someone else, it goes out with
`notes-publish FILE.html` (private until an audience is set with `--audience`), which
serves it on the notes site behind the portal. Say in one line that the page can be
published that way; never publish on your own initiative.
