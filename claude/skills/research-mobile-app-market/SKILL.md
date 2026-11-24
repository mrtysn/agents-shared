---
name: research-mobile-app-market
description: >
  Mobile game and app market research with AppMagic and Sensor Tower: what their
  numbers mean, how far to trust them, which tool fits, and the workflow for
  competitor and genre research or valuing an app. Use when the user asks about
  AppMagic, Sensor Tower, data.ai, app revenue or download estimates, genre or
  niche sizing, competitor games, RpD, retention or DAU benchmarks, or which
  market-intelligence tool to buy.
argument-hint: [game, genre or question to research]
allowed-tools: AskUserQuestion, Read, Glob, Grep, WebSearch, mcp__exa__web_search_exa, mcp__exa__web_fetch_exa
---

# Research the mobile app market

Facts below were read on 2026-11-24 from vendor pages and third-party reviews. Prices and
free-tier limits change: re-check them before quoting.

## Ground truth

- Apple and Google give downloads and revenue to the developer alone. Every outside figure
  is a model over chart ranks, ratings, prices and a panel. No tool publishes an error rate
  that was measured independently.
- AppMagic (games-focused, hand-tagged genres) has been Sensor Tower's small-business tier
  since 2026-05-12; the two keep separate data and methods. Sensor Tower (App Performance,
  Usage, Advertising/Pathmatics) is the enterprise suite, quote only.
- Both are weakest on small apps. AppMagic's own guidance: under 30K downloads or $30K revenue
  a month, take it with a grain of salt; under 10K downloads or $10K revenue, hardly reliable.
  Apps outside every chart in a country count as zero there. Read small apps as bands, and
  trends before levels.

## What the numbers are

- **AppMagic revenue:** net IAP from App Store and Google Play, platform fees excluded, taxes
  included. No ad revenue, no web shop, no alternative stores. Sensor Tower's basis: confirm
  per report.
- **RpD** (revenue per download): close to lifetime value once a game is 6+ months worldwide;
  read it by country and platform; distrust it under 30K downloads a month.
- **Retention** is iOS, **DAU/MAU** is Android, both from a 30M-MAU panel app plus heuristics.
- **Featuring Score:** estimated lift from store featuring, adjusted for duration.
- **Success meter:** share of apps in a tag above a revenue threshold ($100K a month by default);
  finds open niches and "death valleys".
- Two tools can differ by 2x on one app. Align period (calendar month or rolling 30 days),
  scope (worldwide or country, store), gross or net, and iPad plus iPhone listings before
  calling either wrong.

## Free tier (AppMagic, since 2026-01-19)

Rounded worldwide revenue and downloads for any past month; first three genre levels; rank
history to #100,000; Featuring Score. Per-country figures, deep tags and full history are paid.
Paid plans and the API (50+ endpoints) are quoted after a demo; no official price list.
Third-party figures conflict (about $400 to $1,000 a seat a month in 2025; $199 and $399 a month
reported in 2026). Sensor Tower: Vendr's median contract is about $75,000 a year.

## Workflow: competitor and genre research

1. Pick the narrowest tag with a dozen or more apps.
2. Read its success rate over three years: total apps, apps above the threshold, 30-day
   revenue and downloads.
3. Take the top ten by revenue; for each read RpD by country, retention, DAU, release date,
   publisher HQ, LiveOps cadence.
4. Check concentration (top-three share) and the new-versus-established split.
5. Confirm any decision number against a second source.
6. Write period, scope, store and gross or net beside every figure.

## Workflow: valuing or pricing an app

- Treat the estimate as IAP only. Add ads, web shop and off-store subscriptions before comparing
  with company revenue.
- Use growth across months for small apps; the level is the least reliable part.
- Use RpD by country to bound what a download is worth, hence the install price you can pay.
- Validate the tool on apps whose true numbers are known before relying on it.
- No sourced valuation multiples exist in this skill; do not invent one.

## Choosing a tool

First look: AppMagic free. Per-country, retention, DAU, API: AppMagic paid after a trial on
known apps. Ad creatives and spend: Sensor Tower (Pathmatics). Usage panels, non-game apps,
enterprise reporting: Sensor Tower. Sales-call questions: price per seat, countries and history,
export and API limits, whether past estimates are revised, how app identities join across
stores, whether an evaluation on known games is allowed.

## Doing a live look-up

Both sites sit behind the user's login; read [no unprompted account traffic](../../rules/no-unprompted-account-traffic.md)
first. Open pages in the user's own Chrome, one at a time, only for games or genres the user
named, with the user's say-so that an account is connected. Save what a page shows once and
work from the copy. Report each figure with its period, scope and store, and say it is a
modeled estimate. A free-tier figure is rounded: say so.

