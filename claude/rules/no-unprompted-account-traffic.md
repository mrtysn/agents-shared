# Never initiate traffic against the user's logged-in accounts

**Ingesting a list of links is not permission to generate traffic against the
platforms they point at.** The fetchers are for the user to invoke; an agent never
runs one, and never starts one for the user.

Plain HTTP requests for pages, feeds and API responses go through
`fetch-anything-agent get URL`, which leaves from the home address under the gateway's
budget and cool-down; yt-dlp, SDKs and browsers stay direct.

Requests with no login still spend the user's IP budget: fetch once and iterate on
the saved copy, state the count before a loop of more than a handful of requests,
never test network code over ssh on a server, and treat a captcha, consent wall
or 403 block page from a site as the end of requests to that site. A 429 with a
`Retry-After` under 10 minutes is waited out once; a second refusal, or a 429
with no `Retry-After`, ends it. Never record a
refusal as a verdict on a site. A burst limit the agent itself caused (too many
parallel calls to a search tool) is pacing, not a refusal: slow down and continue,
never more than about five in parallel. Where agent-request-limiter answers 429,
stop and tell the user.

The full rule appears the first time a session runs a network command.
