---
name: scrapling
description: >
  Fetch and parse HTML from sites that refuse plain clients — a 403 or 1020 from
  curl/requests, a Cloudflare "checking your browser" page, a JS-rendered page that
  arrives empty, or any scrape that needs browser-grade TLS/headers — using the
  Scrapling Python library (curl_cffi impersonation, Playwright, or a stealth
  Chromium), with the response saved once and all parsing done offline. Use this
  whenever a session is about to scrape, crawl, screen-scrape, or "just fetch the
  page and pull out X" against a site that is not a plain API and not one of
  agent-reach's named platforms, even if the user says curl or requests — and
  always when a first plain fetch was blocked. Not for logged-in pages, posting,
  or anything needing the user's cookies.
allowed-tools: Bash, Read, Write, Edit
---

# Scrapling — blocked-site fetching and offline parsing

Scrapling is one library with three fetchers of increasing weight and one lxml-based
`Selector` that parses whatever any of them returns. Tested here at **0.4.15**
(Python 3.12, macOS arm64). The value is the middle rung: `Fetcher` with
`impersonate="chrome"` is a single TLS-fingerprinted request — no browser — and it
got a 200 with full HTML from a Cloudflare-fronted site that serves curl a challenge.

## Choose the tool first

| Situation | Use |
|---|---|
| Plain API, RSS, static page that answers curl | `curl` — nothing here is needed |
| YouTube, Reddit, GitHub, X, podcasts, stock quotes, web search | `agent-reach` skill (it routes per platform) |
| Site answers curl/requests with 403/1020/429 or a Cloudflare interstitial; page needs Chrome-like TLS | **Scrapling `Fetcher`** with `impersonate` |
| Content only exists after JavaScript runs | **`DynamicFetcher`** (Playwright Chromium, headless) |
| Bot check that a plain headless browser fails | **`StealthyFetcher`** (patched Chromium, fingerprint spoofing) |
| Page behind the user's login | none of these — see `no-unprompted-account-traffic`; no cookies, ever |

Climb one rung at a time, and only after the lower rung was actually refused. Each rung
costs more requests per page (a browser loads subresources) and looks more like abuse.

## The request budget is the whole discipline

These follow from the user's `no-unprompted-account-traffic` rule and are not optional:

1. **Fetch once, iterate on the saved copy.** Every fetch writes the body and headers to
   disk (the bundled script does this). Selectors are developed against the file with
   `Selector(open(path,'rb').read())`. Re-running a fetch to test a parser is the
   failure this rule exists for.
2. **State the count before a loop.** Before any command that will make more than a
   handful of requests to one host, say how many and to what, and wait. Tens against one
   host within an hour is already too many.
3. **The first refusal ends it.** A 403, 429, 1020, captcha, Turnstile, consent wall or
   "sorry" page means stop, save what came back, and report. No retry, no header
   variation, no climbing to the next fetcher without telling the user what was refused.
4. **Robots first.** Read `robots.txt` (that is one request; cache it) and stay out of
   disallowed paths. Scrapling's `Spider` class defaults to `robots_txt_obey=False` —
   do not use the spider/crawler templates at all; one page at a time, by hand.
5. **A browser fetch is many requests.** Count a page load as at least one plus its
   scripts. Keep `disable_resources=True` (drops images, fonts, media, stylesheets) and
   never let a browser fetcher run on an interval.
6. **Never test network code from a server.** Run fetches from the local machine, through
   the proxy, so the limiter counts them.
7. **`solve_cloudflare=True` stays off** unless the user explicitly asks — it drives
   repeated challenge traffic at the site under the user's IP.

## The machine's HTTPS proxy (agent-request-limiter)

The session exports `HTTPS_PROXY`, `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`.

- `Fetcher` (curl_cffi) honours both automatically. Verified: requests appeared in the
  limiter's per-site counts, no certificate errors.
- **Browser fetchers ignore `HTTPS_PROXY`.** Chromium reads system proxy settings, not
  env vars, and Scrapling only passes a proxy to Playwright when given one. A
  `DynamicFetcher.fetch(url)` with no `proxy=` went straight out, uncounted. Always pass
  `proxy=os.environ["HTTPS_PROXY"]`. Verified: with it, the stealth fetch was counted.
- `StealthyFetcher` sets `ignore_https_errors=True` on its context, so the limiter's
  MITM certificate is accepted. `DynamicFetcher` does not; if it raises a certificate
  error through the proxy, pass `additional_args={"ignore_https_errors": True}` once.
  If that also fails, report it. Never install the limiter's CA into Chromium or the
  system store, and never route around the proxy to make a fetch succeed.
- A 429 carrying an `X-Agent-Request-Limiter` header is the limiter refusing, not the
  site: stop, tell the user which site and how many requests the task needed.

## Install

Base package is parser-only. The fetchers are an extra, and the browsers are a
further step.

```bash
# throwaway or per-project, never system Python
uv venv .venv && uv pip install --python .venv/bin/python 'scrapling[fetchers]'
# or, for one script without managing a venv:
uv run --with 'scrapling[fetchers]' script.py
```

| Fetcher | Needs | Size |
|---|---|---|
| `Fetcher` / `AsyncFetcher` | `scrapling[fetchers]` (curl_cffi) | small |
| `DynamicFetcher` | + Playwright Chromium: `.venv/bin/python -m playwright install chromium` | ~150 MB download |
| `StealthyFetcher` | same Chromium build (patchright shares `~/Library/Caches/ms-playwright`) | none extra |

Check `ls ~/Library/Caches/ms-playwright` before downloading — a matching `chromium-<rev>`
may already exist from another project (`python -m playwright install --dry-run chromium`
prints the revision it wants). `scrapling install` does the same download plus
`install-deps`; on macOS the plain playwright command is enough.

The `scrapling` CLI (`scrapling extract get|fetch|stealthy-fetch URL out.html`) exists but
the script below records status, headers and redirect chain, which the CLI does not.

## Fetch with the bundled script

`scripts/fetch_once.py` makes exactly one fetch per process, saves
`<out>/<name>.html` + `<name>.meta.json`, passes `HTTPS_PROXY` to the browser fetchers,
never retries, and exits 3 on any 4xx/5xx so a loop cannot silently continue.

```bash
S=~/.claude/skills/scrapling/scripts/fetch_once.py   # symlinked by init-global.sh
uv run --with 'scrapling[fetchers]' "$S" plain    https://example.com/page  ./responses
uv run --with 'scrapling[fetchers]' "$S" dynamic  https://example.com/app   ./responses --wait-selector '#list'
uv run --with 'scrapling[fetchers]' "$S" stealthy https://example.com/page  ./responses
```

## Minimal worked examples (the API behind the script)

```python
import os
from scrapling.fetchers import Fetcher, DynamicFetcher, StealthyFetcher
from scrapling.parser import Selector

# 1. Plain, impersonated — one HTTP request, proxy + CA bundle from env.
r = Fetcher.get(url, impersonate="chrome", stealthy_headers=True, timeout=30, retries=0)
r.status, r.headers, r.body            # save these
r.css("title::text").get()             # Response is itself a Selector

# 2. Browser (JS-rendered). Proxy MUST be explicit.
r = DynamicFetcher.fetch(url, headless=True, disable_resources=True,
                         proxy=os.environ["HTTPS_PROXY"], wait_selector="#content", timeout=45000)

# 3. Stealth browser. Same shape; solve_cloudflare stays False.
r = StealthyFetcher.fetch(url, headless=True, disable_resources=True, block_webrtc=True,
                          solve_cloudflare=False, proxy=os.environ["HTTPS_PROXY"], timeout=45000)

# 4. Parse offline from the saved copy — every iteration after the fetch.
page = Selector(open("responses/page.html", "rb").read(), url=url)
page.css("h1::text").get()
page.css("a[href]::attr(href)").getall()
page.find_by_text("Moby-Dick", partial=True)      # element whose text contains it
page.css("div.item")[0].get_all_text(strip=True)
```

`retries=0` matters: the default retries on transport errors, which is a hidden loop.

### Adaptive selectors — what they actually do

`Selector(..., adaptive=True, storage_args={"storage_file": "<your>.db", "url": url})`,
then `page.css("h1", identifier="title", auto_save=True)` stores the element's
fingerprint; later `page.css("h1", identifier="title", adaptive=True)` relocates it after
the markup changed. Verified offline on saved copies:

- tag and attributes changed, same DOM position → relocated correctly;
- element moved one level deeper → wrong sibling at 67% similarity, nothing at the
  default `percentage=80`. Relocation is position-weighted; a structural move defeats it.

Always pass `storage_args` with your own `storage_file`: the default writes
`elements_storage.db` inside the installed package directory.

## Gotchas hit during evaluation

- `stealthy_headers=True` (the default for `Fetcher`) fabricates `Referer: https://www.google.com/`.
  Pass `headers={"Referer": None}` or `stealthy_headers=False` when that is dishonest for the task.
- `uv pip install 'scrapling[fetchers]'` pulls playwright **and** patchright (~40 MB each);
  the first attempt timed out through the proxy on the patchright wheel. Retry the package
  install once with `UV_HTTP_TIMEOUT=300` — that is PyPI traffic, not target-site traffic.
- `httpbin.org/html` has no `<title>`; `css("title::text").get()` returns `None`, not an
  error. Check `.get()` results before slicing.
- The `Response.history` list is empty unless a redirect happened; `final_url` is `r.url`.
- The Cloudflare-fronted test site answered the impersonated `Fetcher` with 200 and set
  cookies in the response. Those cookies were not stored or replayed; `Fetcher.get` is
  stateless per call unless you use `FetcherSession`, which you should not for this policy.
- `DynamicFetcher` through the proxy is **untested** (budget); the certificate path above
  is the expected behaviour from the source, not a measurement.
