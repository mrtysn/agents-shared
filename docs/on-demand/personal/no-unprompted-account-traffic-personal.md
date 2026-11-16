# Account traffic on the personal machine: full text

The personal-profile half of `docs/on-demand/no-unprompted-account-traffic.md`: the
gateway, proxy and logins that exist only on the owner's own machines. Everything there holds
here too.

## Plain HTTP requests go through the gateway

A request for a page, feed or API response that curl or a script would make goes through `fetch-anything-agent get URL`
(also `record KIND KEY` and `status`). The gateway counts it against the site's budget,
answers repeats from its archive, and cools the site after a refusal, with a 429's
`Retry-After` setting the wait. The `agents` token is pinned to the home address, so
the Mac's runner serves every fetch: with it stopped the answer stays queued (HTTP 202)
and nothing arrives. A site the owner's tools depend on (Steam, TEFAS and the other
committed rules in fetch-anything's `sites/`) answers 403 `scope`; that is the gateway's
scope check, not a refusal by the site, so use the owner's tool for it or ask. yt-dlp,
SDKs, browsers and anything else that does its own HTTP stay direct under the refusal
rules of the shared doc.

A refusal the gateway reports is its cool-down for the site: wait it out, do not re-send.

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

## agent-request-limiter

On this machine, agents' requests go through a per-site budget proxy (via the proxy settings
every session gets; a tool that ignores them is not counted, so never reach for one to get around it). A refusal is an
HTTP 429 carrying an `X-Agent-Request-Limiter` header. On one: stop requesting that site and tell the
user what you were doing and how many requests it needed. **Never** retry it, route around the proxy,
edit its tier or state files, stop or restart it, or run its `approve`/`deny`/`ask` commands. Raising
a site's tier is the user's decision alone.

## Provenance

Oct 20 2026, job-search: a session reported "I can't sign in through Authelia" and reviewed
jobs.mertyas.in from local renders. It had sent no request; the agent-login mechanism had
existed since Oct 17 and this doc, which the session saw at its first ssh, did not mention
it. The Authelia section above is the result.

Oct 14 2026: asked whether requests should stop at a site's first refusal, the user
chose one retry after a `Retry-After` for requests that do not go through
fetch-anything, and had written that requests should "learn and adapt its pacing"
instead of ending early. A 429 exception was the result, since replaced by the Oct 24
entry in the shared doc.
