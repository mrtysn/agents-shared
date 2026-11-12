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
- **A refusal mid-run** (a 403, "you have been blocked"): stop every request to that shop for
  the day, mark its cells "not checked" on the page, and record it in the rule's `reach`. Each
  search counts against the user's own browser, and a shop remembers the day before: n11,
  MediaMarkt and Hepsiburada all refused on 2026-11-12 after two days of searching.
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
