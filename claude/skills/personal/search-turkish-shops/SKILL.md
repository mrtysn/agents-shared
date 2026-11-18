---
name: search-turkish-shops
description: Find and price products the user wants to buy in Turkey, across the known Turkish shops (marketplaces, electronics chains, D&R and others), in the user's Chrome. Use when the user asks what something costs, where to buy it, for deals or alternatives, or for a shopping or price-comparison page. Lists the shops from fetch-anything's rules, shortlists models before searching, and reads each shop's own JSON or search HTML with one request per model.
argument-hint: [what to buy, e.g. "earbuds with a good mic"]
allowed-tools: Bash, Read, Write, Edit, Agent, mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__browser_batch, mcp__claude-in-chrome__select_browser, mcp__claude-in-chrome__computer
---

# search-turkish-shops

## The shops

The list of shops lives in fetch-anything's site rules, one `sites/<shop>.json` each, in its
`retail` block: name, kind, categories, search URL (`{q}` is the encoded query), the pattern a
product URL matches, and `reach` (how the shop answered the user's Chrome and the box, and when).

```bash
fetch-anything-agent shops --json                 # every shop
fetch-anything-agent shops --category audio       # only shops that sell audio
```

Prices come only from these shops. Never from an aggregator (Akakçe, Cimri, Epey): they miss
daily deals and list junk resellers. A shop the user names that is not listed is checked in
Chrome first, then added as a rule with its `retail` block (fetch-anything's `CLAUDE.md` holds the
rule format; `tests/test_retail_rules.py` checks it). When a shop answers differently from its
`reach` (a new human check, a block), update `reach` and `checked` in the same commit.

## Discovery: shortlist first, then one request per model

1. **Shortlist before searching.** Decide the models from what the user asked for and from review
   sources (RTINGS for audio and TVs), about two per brand. Never pull a shop's whole category or
   search every model name you can think of.
2. **One request per shortlisted model per shop**, at least 3 seconds apart, run from a tab already
   open on that shop, with `fetch()` of the shop's own search endpoint, parsed in the page. No
   hidden iframes and no page-by-page navigation: both load every asset and get the browser
   throttled or challenged.
3. **Small shops** (D&R, Idefix, music stores): read the shop's menu and the category that
   holds the product (music stores keep consumer headphones under LIFESTYLE or Hi-Fi), and its
   brand filter; search only the brands it carries. A shop is written off for a product only
   after its categories are read and its "no result" message is seen on screen, never from an
   empty read of a page still loading.
4. **Read structured data where the shop has it**: embedded state or JSON (MediaMarkt's
   `__PRELOADED_STATE__.apolloState`) beats parsing cards. `readers.md` has the reader for each shop
   that has one.

## Reading in Chrome

- Load the claude-in-chrome tools and select the browser per the chrome-bridge memory.
- **A human check** (Cloudflare checkbox, "Güvenlik" page): open the tab, ask the user to click,
  and carry on with other shops. Never click a check yourself.
- **A refusal** (a 403, "you have been blocked", Cloudflare's "Attention Required"): stop
  requests to that shop and mark its cells "not checked". Then load one other shop's home page:
  if several shops refuse even their home page, the cause is the network, not the searching.
  Ask the user whether a VPN is on. A commercial VPN exit is a datacenter address that these
  shops block. On 2026-11-12, n11, MediaMarkt, Pazarama and PttAVM refused, and Hepsiburada
  challenged, through a Mullvad exit, and all five served normally once it was off.
- **Long runs**: a `javascript_tool` call times out at 45 s. Start the loop without awaiting it,
  save the result to `localStorage` when it ends, and read it in a later call. A Chrome restart
  or a disconnect kills the loop; the saved result survives.
- **Long output**: tool output is cut near 1,000 characters. Write the result into the page body
  (`<pre>`) and read it with `get_page_text`.

## What goes on the page

- Every price is a link to the listing it was read from. Collect `(price, url)` together.
- In stock only. A price shown only in the cart is marked `cart`.
- A listing whose name or URL names a different model (FreeBuds 6i under FreeBuds 6, a Pro Max
  under Pro) is dropped, not reported as the model.
- Installment lines (`9 x 303,22 TL`) are not prices.
- List the facts, not a pick, unless the user asks for a recommendation.
- **A model name is a link too**: the first cell of a row links to that model's cheapest listing.
  Only a missing-listing cell (`—`, `not listed`) or an unread shop (`not checked`) is plain text,
  and no cell is empty. A price the user supplied (a screenshot) says so and links to the shop's
  product page.
- **Say what stock was checked.** "In stock only" holds where the shop's own data states stock
  (MediaMarkt's `isAvailableAndBuyable`) or the listing page was opened. Otherwise the opening
  paragraph says stock was not opened per listing, and which shops it was read for.
- **Order**: the verdict or read, then specs and performance, then prices, then notes, sources last.
  Every spec claim comes from a page that was read, linked in the sources.
- **Price tables stay narrow**: `Model | Cheapest | Other shops` with each price linked, not one
  column per shop. A table of more than about five columns scrolls sideways and hides the right-hand
  shops (the 2026-11-17 sticks page had nine).
- **One topic, one page.** A later step on the same topic (a comparison, a review digest, a
  correction) is a new section of the existing page, re-rendered from its Markdown source.
  `page-new` never overwrites: render to a scratch file and copy it over the old page.
- **Before reporting, check the HTML**: every first-column cell and every price cell holds an
  `<a href`. A page that fails this has been sent back before.

## After the page: file it in inventory

Inventory is the shopping hub: one wanted thing per need, holding its research page, then its
purchase and warranty. Run the `inventory` command from the folder the session started in.

1. **File the need, once per topic.** `inventory find "<need>" --lifecycle wanted` first; a later
   session on the same topic attaches to the thing that exists. Otherwise
   `inventory add "<need, e.g. earbuds for calls>" --lifecycle wanted`. Name it for the need, not a
   model: the page is the candidate list. It lands as a draft in the Inbox for the user to keep.
2. **Attach the page as one file.** `project-lifecycle page-bundle PAGE.html --out <scratchpad>/PAGE.html`,
   then `inventory attach THING <scratchpad>/PAGE.html --label research`. A raw notebook page links
   `ws/` and local images and renders bare inside inventory. A re-rendered page goes up with
   `--replace ATT` naming the old attachment (the `att#` number `inventory show THING` prints).
3. **A price-watch** the user set up for it is stored with `inventory edit THING --link Watch=URL`.
4. **When the user says it was bought:** `inventory purchase THING --shop S --price P --date
   YYYY-MM-DD --url LISTING`, then `inventory edit THING --maker M --model M --lifecycle in_use`.
   Attach the order mail as a PDF with `attach` when the user gives it.
