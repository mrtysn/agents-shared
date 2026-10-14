# Never initiate traffic against the user's logged-in accounts

**Ingesting a list of links is not permission to generate traffic against the
platforms they point at.** The fetchers are for the user to invoke; an agent never
runs one, and never starts one for the user.

Requests with no login still spend the user's IP budget: fetch once and iterate on
the saved copy, state the count before a loop of more than a handful of requests,
never test network code over ssh on a server, and treat a 429, 403, captcha or
consent wall from a site as the end of requests to that site. Never record a
refusal as a verdict on a site. A burst limit the agent itself caused (too many
parallel calls to a search tool) is pacing, not a refusal: slow down and continue,
never more than about five in parallel. Where agent-request-limiter answers 429,
stop and tell the user.

The full rule appears the first time a session runs a network command.
