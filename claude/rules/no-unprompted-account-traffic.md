# Never initiate traffic against the user's logged-in accounts

**Ingesting a list of links is not permission to generate traffic against the
platforms they point at.** The fetchers are for the user to invoke; an agent never
runs one, and never starts one for the user.

Requests with no login still spend the user's IP budget: fetch once and iterate on
the saved copy, state the count before a loop of more than a handful of requests,
never test network code over ssh on a server. A refusal slows the task, it does not
end it: a bot check (Cloudflare's "Just a moment", a captcha) wants a browser: when the
user asked for exactly that page and the site holds no login of theirs, open it in their
Chrome, one page at a time; otherwise say the page needs a browser and open it on a yes.
A 403 or 429 is retried after a pause (its
`Retry-After`, else a minute or more), and only three refusals spread over several
minutes end requests to that site, with what was tried reported. Never record a
refusal as a verdict on a site. A burst limit the agent itself caused (too many
parallel calls to a search tool) is pacing, not a refusal: slow down and continue,
never more than about five in parallel. Where a request-budget proxy the machine runs
answers 429 with its own refusal header, stop and tell the user.

A tool an agent builds that loads pages in the user's browser is held to the same: it
paces from each site's robots.txt (a slow floor when unreadable), stops a site at its
first refusal (the one place a first refusal still ends it), and is never updated mid-run.

The full rule appears the first time a session runs a network command.
