# Never initiate traffic against the user's logged-in accounts

**The fetchers exist for the user to invoke, not for an agent to run because
links appeared.** Ingesting a list of links is not permission to generate
traffic against the platforms they point at.

It is the user's real account and their risk budget — rate limits, automated-
access flags, and bans land on them, not on the session that offered to be
helpful. A bulk pass over someone's saved posts is exactly the shape of traffic
platforms act on.

## What to do instead

- Bare links go onto a worklist. That costs nothing and loses nothing.
- Content arrives when the user captures pages themselves, or when they run the
  fetcher. Both already exist; neither is yours to trigger.
- Never propose a bulk fetch against the user's own session. If they want it,
  they will say so.

## No session attached is not a free pass

**The user's IP addresses are their identity too** — the home connection and every
server they run. A rate limit or "unusual traffic" flag on those lands on them
exactly as an account flag would: captchas in their own browser, and a production
job on the server that stops working. So requests with no login still spend the
user's budget, and these hold for any third-party service:

- **Fetch once, iterate on the copy.** Save the response to the scratchpad and
  develop parsers, matchers and decoders against the saved file. Re-running a
  fetching script to test the code after it is the failure this section exists for.
- **State the count before a loop.** Before any command that makes more than a
  handful of requests to one service, say how many and to what. Tens against one
  host within an hour is already too many for testing.
- **Never test network code on a server.** Running a script over ssh — `docker exec` into a
  production container included — sends its requests from that server's IP, where nothing counts
  them and a ban hits production. Test locally against a saved response; run network code on a
  server only when the user asked for exactly that. `hooks/ssh-request-guard.sh` asks the user
  whenever an ssh command would run network-capable code remotely.
- **Undocumented endpoints need a yes first.** An internal API a site's own page
  calls (Google's `batchexecute`, a mobile app's private API, a scraped JSON
  route) gets the user's approval before the first request, with the plan for
  how often production will call it.
- **The first refusal ends it.** A 429, a 403, a captcha, a consent wall or a
  "sorry" page means stop and report. No retry, no header variations, no second
  host to try from — each of those is another request against a service that
  already said no.
- **Production code backs off by itself.** Anything shipped that calls a
  third-party service caches what it fetched, and after a refusal stops calling
  for a cool-down period instead of trying again on the next run.

Fetching a single public page the user pointed at is ordinary work.

## agent-request-limiter

Where it is installed, every agent request goes through a per-site budget proxy. A refusal is an
HTTP 429 carrying an `X-Agent-Request-Limiter` header. On one: stop requesting that site and tell the
user what you were doing and how many requests it needed. **Never** retry it, route around the proxy,
edit its tier or state files, stop or restart it, or run its `approve`/`deny`/`ask` commands. Raising
a site's tier is the user's decision alone.

## Provenance

Sep 22 2026: building a news-link resolver, about 100 requests went to Google in
90 minutes from the home IP and node01 — the RSS searches re-fetched on every
test run, the undocumented decoding endpoint hit repeatedly, and node01 kept
probing past a consent wall. Google answered 429 from both addresses. The rule
above had exempted sessionless fetches; that exemption is what the section
replaces.
