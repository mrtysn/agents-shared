---
description: Find interesting repositories on GitHub, GitLab, Codeberg and SourceHut for a topic or need. Use when user asks "find a cool repo for X", "what's a good project for X", "is there a library that does X", wants to browse what is new or rising in a topic, or invokes /discover-repos. For Claude Code skills use discover-skills instead.
context: fork
allowed-tools: WebSearch, Bash(gh search:*), Bash(gh api:*), Bash(fetch-anything-agent get:*), Bash(jq:*), Bash(tail:*), Bash(sed:*)
argument-hint: <topic or need> [rising|established]
---

# discover-repos

Find repositories for: **$ARGUMENTS**

If no arguments were given, return immediately asking for a topic or need — do not search on a guessed query.

An optional trailing `rising` biases toward repos created in the last 90 days; `established` (the default) biases toward stars. Today's date is in your context: compute the date cutoffs from it, never hardcode them.

## Sources

Run all of these in parallel in one turn. Every command asks for 15 results or fewer: this is about 5 requests in total, so no loop confirmation is needed.

| Source | Command |
|--------|---------|
| GitHub by topic | `gh search repos --topic <topic> --stars ">100" --updated ">=<today minus 365d>" --sort stars --limit 15 --json fullName,description,stargazersCount,pushedAt,language,url` |
| GitHub by keyword | `gh search repos "<keywords>" --stars ">50" --sort stars --limit 15 --json fullName,description,stargazersCount,pushedAt,language,url` |
| GitHub rising | same as keyword, with `--created ">=<today minus 90d>" --stars ">20"` replacing `--stars ">50"`. Always run it when the argument says `rising`; otherwise run it too, it is cheap |
| GitHub awesome lists | `gh search repos "awesome <topic>" --sort stars --limit 5 --json fullName,description,stargazersCount,url` — an awesome list is often the best single hit; open its README (`gh api repos/<owner>/<repo>/readme -H "Accept: application/vnd.github.raw"`) only if the repos above are thin |
| GitLab | `fetch-anything-agent get 'https://gitlab.com/api/v4/projects?search=<q>&order_by=star_count&sort=desc&per_page=15&simple=true'` |
| Codeberg | `fetch-anything-agent get 'https://codeberg.org/api/v1/repos/search?q=<q>&sort=stars&order=desc&limit=15'` |
| SourceHut | `fetch-anything-agent get 'https://sr.ht/projects?search=<q>'` — HTML only, no stars. Each project is an `<a href="/~owner/name/">` followed by a `<p>` description |

`fetch-anything-agent get` prints a two-line `[fresh, fetched …]` header before the body; drop it with `tail -n +3` before piping to `jq`. GitLab returns a bare JSON array (use `name_with_namespace`, `description`, `star_count`, `last_activity_at`, `web_url`). Codeberg wraps it as `{"ok":…,"data":[…]}` (use `full_name`, `description`, `stars_count`, `updated_at`, `html_url`).

Bitbucket has no usable public repository search any more (its API answers "no API hosted at this URL"); do not try it.

Plain web search is the fallback for a niche topic: WebSearch `<topic> github OR gitlab OR codeberg`.

## Limits

- Fetch once and work from what came back; do not re-query to paginate unless the user asks.
- A 429, captcha, consent wall or 403 from a host ends requests to that host. Report it and carry on with the others.
- GitLab and Codeberg are small next to GitHub and mostly hold their own projects or mirrors; a thin result there is normal, not a failure.

## Report

Rank by how interesting the repo is, not by stars alone: recent pushes, a clear one-line purpose, a licence, and a fit with the ask. Drop forks, archived repos, tutorials-only repos and anything with no push in two years unless it is the only hit.

One table, at most 10 rows, columns: repo (as a link), host, stars (`–` where the host gives none), last push, what it is in one clause. Below it, one line naming the single best pick and why. If a host failed or returned nothing, say so in one line.
