---
description: Search the owner's Link Keeper saved links by their content: titles, URLs, tags, notes, captured page text, X posts, and Instagram reel transcripts and on-screen text. Use when the user asks to find a saved link, a repo, a reel, a post or something they "saved about X", or invokes /search-saved-links. For finding new repos use discover-repos instead.
context: fork
allowed-tools: Bash(search-saved-links:*), Bash(link-keeper link:*), Bash(link-keeper capture:*)
argument-hint: <words to find>
---

# search-saved-links

Find saved links matching: **$ARGUMENTS**

If no arguments were given, return immediately asking what to look for.

## Run

```
search-saved-links WORDS... --limit 15
```

Every word must match (any order, anywhere in the link's text); the best match is first and each hit shows a snippet of captured text around the first matching word. Narrow with `--site HOST` or `--tag T`; add `--json` to parse the result. It reads Link Keeper live from Firefox, else from the latest backup.

- It matches words and word forms (`swimming` finds `swim`), not meaning. A query about an idea needs the words the text would use: try two or three phrasings in parallel when the first returns nothing.
- Repos are links: search the repo's name, or `github` plus a topic word. A reel's tools and repos are in its `about` text, so they match too.
- Images are not searched. A capture holds an image's address, not its pixels; a reel's on-screen text is searched.

## Opening one result

`link-keeper link URL --text` prints one link in full and `link-keeper capture URL` its captured text, links and images. Use them only for the one or two hits the user needs, never to read every hit.

## Report

A table of at most 10 rows: title (linked), date, tags, and one clause on why it matches. End with the count line the command prints. If nothing matched, say which phrasings were tried.

The saved links include private messages and DMs. Report what was asked for; never paste long captured text, and never write results anywhere outside the reply.
