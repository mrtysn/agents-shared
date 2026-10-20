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
- When links pile up, an agent may say once, in a line, that the fetcher exists
  and how many links are waiting. It never runs the fetcher, never starts it for
  the user, and never repeats the mention in the same session.

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
- **Public code and docs hosts are ordinary reads.** Raw files and pages on GitHub, GitLab
  and official docs sites need no count stated up front, up to about 15 distinct URLs per
  task, each fetched once and saved. Past that, state the count first. A refusal still ends it,
  as below. This does not cover search-engine pages, undocumented endpoints, anything
  behind a login, or any run on a server.
- **Plain HTTP requests go through the gateway.** A request for a page, feed or API
  response that curl or a script would make goes through `fetch-anything-agent get URL`
  (also `record KIND KEY` and `status`). The gateway counts it against the site's budget,
  answers repeats from its archive, and cools the site after a refusal, with a 429's
  `Retry-After` setting the wait. The `agents` token is pinned to the home address, so
  the Mac's runner serves every fetch: with it stopped the answer stays queued (HTTP 202)
  and nothing arrives. A site the owner's tools depend on (Steam, TEFAS and the other
  committed rules in fetch-anything's `sites/`) answers 403 `scope`; that is the gateway's
  scope check, not a refusal by the site, so use the owner's tool for it or ask. yt-dlp,
  SDKs, browsers and anything else that does its own HTTP stay direct under the refusal
  rules in this file.
- **Never test network code on a server.** Running a script over ssh — `docker exec` into a
  production container included — sends its requests from that server's IP, where nothing counts
  them and a ban hits production. Test locally against a saved response; run network code on a
  server only when the user asked for exactly that. `hooks/ssh-request-guard.sh` asks the user
  whenever an ssh command would run network-capable code remotely.
- **Undocumented endpoints need a yes first.** An internal API a site's own page
  calls (Google's `batchexecute`, a mobile app's private API, a scraped JSON
  route) gets the user's approval before the first request, with the plan for
  how often production will call it.
- **A refusal ends it, except a 429 that says when to come back.** A captcha, a
  consent wall, a "sorry" page or a 403 block page means stop and report. A 429
  that carries a `Retry-After` of under 10 minutes is waited out once: wait that
  long, send one more request, and stop and report if it is refused again. A 429
  with no `Retry-After`, or a longer one, means stop and report. No header
  variations, no second host to try from — each of those is another request
  against a service that already said no.
- **A refusal is never written down as a verdict on the site.** "Ends it" covers
  requests from this session, nothing more. Do not record the host as excluded,
  blocked, banned or "failed" in a skill, rule, memory, script or doc; a one-off
  429 or 403 says nothing about the site tomorrow. A skill's source list is
  changed only when the user asks, and a source you could not use is reported in
  that reply, not removed from the list.
- **A burst limit you caused is pacing, not a refusal.** When a search or research
  tool the session itself calls (Exa, web search) answers 429 because the agent sent
  too many calls at once, slow down and continue: send the remaining queries one or
  two at a time, never more than about five in parallel. Abandoning the research over
  your own burst is the wrong lesson. This does not cover a target site's 429, which
  follows the 429 rule above.
- **Production code backs off by itself.** Anything shipped that calls a
  third-party service caches what it fetched, and after a refusal stops calling
  for a cool-down period instead of trying again on the next run.

Fetching a single public page the user pointed at is ordinary work.

## The user's own sites behind Authelia

Sites on `*.mertyas.in` sit behind Authelia, and Authelia accepts a Basic `Authorization`
header from an agent login named `agent-<folder>`, where the folder is the one holding
the repository's main checkout. `agent-auth` (in `~/bin`, from the `tools` repo) derives
the login from the current folder and fetches its password from Doppler:

    curl -sS -H "$(agent-auth header)" https://<site>.mertyas.in/...

The request goes direct, never through `fetch-anything-agent`: the gateway is for
third-party pages, carries no headers and would archive a signed-in response. A login
exists only for folders the owner has opened on the box, each to named sites; `agent-auth
whoami` prints the login this folder would use, and `header` fails with a Doppler message
when none exists. On a 401, run `agent-auth refused` and stop: Authelia locks the login
for about five minutes after wrong tries, and a retry extends the lock. Design and the
server-side steps: `homelab/docs/agent-sign-in-plan.html`.

An agent never says a gated site cannot be reached without having run the request. When
the login is missing, report that the folder has no login yet; rendering the page locally
is a workaround to name as one, not a substitute.

## Tools that send requests from the user's browser

A browser extension, userscript or app an agent builds that loads pages in the user's own browser
sends its traffic from their address and with their logins, so the sites see the user, not a bot.
Everything above binds what the tool does, not only what the session does, and these hold before it
ships:

- **Pace from the site's own word.** Read each site's robots.txt once before its first page and never go
  faster than its `Crawl-delay`; a robots.txt that cannot be read (a timeout, a server error) means a
  slow floor of about 30 s, not none. Waits not given by the site start at about 10 s between pages of one
  site, never a figure picked to make a run finish sooner. A setting that speeds the tool up never goes
  below the site's floor.
- **Recognise a refusal and stop at the first one.** A login page the site redirected to, a captcha, a
  block or rate-limit page ("not able to serve your requests this quickly", "unusual traffic") ends that
  site for the run. A refusal the tool cannot recognise it cannot obey, so its tests include the pages
  of the sites it will actually reach.
- **Check the pace against the site, not against the tool.** A monitor that compares the tool's timing
  with the tool's own table only proves the table was followed. Report the real gap per site and
  every refusal.
- **Never update the tool while it runs.** Installing a new version of an extension mid-run restarts it
  and drops the run; release between runs.
- **Keeping why a link failed, when the user asks for it,** is data they retry from, not a verdict on the
  site, and the clause above about not recording refusals does not forbid it.

## agent-request-limiter

Where it is installed, agents' requests go through a per-site budget proxy (via the proxy settings
every session gets; a tool that ignores them is not counted, so never reach for one to get around it). A refusal is an
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

Oct 9 2026: fifteen parallel Exa searches hit its ten-per-second limit and the
session dropped the five failed lookups under "the first refusal ends it". The
user: "you can pace your queries, dont stop searching for info cos of a mistake
you made". The burst-limit clause above is the result.

Oct 20 2026, link-keeper: a capture queue an agent built loaded the user's saved links in their own
Firefox at 2 s per site, a figure no site gave. Hacker News, whose robots.txt asks for 30 s, got 32 pages
in minutes and rate-limited the user, whose message was "WTF FIX THE TOOL WHY IS IT GETTING ME BANNED FROM
HACKER NEWS". Its refusal page was not recognised, so the run could not stop; the session's monitor
reported "spacing fine" because it checked the tool against its own table; and eight releases in under
three hours, several mid-run, reset the user's run four times. The browser-tools section is the result.

Oct 20 2026, job-search: a session reported "I can't sign in through Authelia" and reviewed
jobs.mertyas.in from local renders. It had sent no request; the agent-login mechanism had
existed since Oct 17 and this doc, which the session saw at its first ssh, did not mention
it. The Authelia section above is the result.

Oct 14 2026: asked whether requests should stop at a site's first refusal, the user
chose one retry after a `Retry-After` for requests that do not go through
fetch-anything, and had written that requests should "learn and adapt its pacing"
instead of ending early. The 429 exception above is the result.
