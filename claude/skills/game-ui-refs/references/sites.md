# Reference sites

Surveyed 2026-09-14. Every row was fetched, not recalled. Terms move — when a site's
behaviour contradicts its row, trust the site and fix the row.

**Access** decides what the skill may do with a site:

| Access | Meaning |
|---|---|
| `chrome` | Free, no login, but visual or closed to plain fetches. View it in a Chrome tab. |
| `fetch` | Free, no login, and the content is text WebFetch returns. Fetch it. |
| `links` | Needs an account or a paid plan, or its terms forbid automated access outright. Compose deep links for the user; do not load the pages. |

## 1. Game UI libraries — screenshots and video of shipped games

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [Game UI Database](https://www.gameuidatabase.com/) | `chrome` | The default. ~1,700 games, ~69k screens, video clips; the deepest screen taxonomy anywhere | `index.php?set=1&scrn=<id>&plat=<id>&tag=<id,id>` — IDs in [guidb-ids.md](guidb-ids.md). `vid=1` videos only, `hex=<rrggbb>` colour, `text=<words>` text in images. One screen: the listing URL plus `&autoload=<screen id>`, which the site's viewer sets on click. Listings page at 50 screens | Cloudflare-challenges plain fetches (403). Footer (live, 2026-09-14): *"All content present on this website is explicitly prohibited from being employed in any manner pertaining to AI asset generation, machine learning or cryptocurrency initiatives."* robots.txt: `Content-Signal: search=yes,ai-train=no` (ai-input unset), and disallows named AI agents including `ChatGPT-User` and `Claude-Web`. Kept at `chrome` (2026-09-14): the skill reads a handful of pages to answer one question, which the content signal does not restrict, and never trains on or stores the content |
| [Interface In Game](https://interfaceingame.com/) | `chrome` | Second opinion; ~16k screens, clean per-game galleries | `/screenshots/?elements=<slug>&genres=<slug>&themes=<slug>`. Elements: `character credits dialogue game-over in-game inventory level-selection loading lobby main-menu map overlay progress quest scoreboard settings skill-tree start-screen stats store tutorial`. Genres: `action adventure card-game fighting fps indie mmo music platformer puzzle racing rpg simulation sport strategy`. Themes: `cartoon fantasy horror medieval military modern pirate pixel-art sci-fi western`. Platform: `platforms=mobile` (confirmed; 1,655 screens). One screen: `/screenshots/<game-slug>-<caption-slug>/`. No pause, popup or reward element — fall back to `overlay` or `in-game` | WebFetch 403. Terms bar using the site "to spider, crawl, or scrape"; no AI clause |
| [HUDS+GUIS](https://www.hudsandguis.com/home/category/Games) | `chrome` | Stylised, fiction-grade interfaces | `/home/category/Games`, `/home/tag/<tag>` | Mostly film/TV; last game post Nov 2024 |
| [Video Game Loading Interface Archive](https://loadinginterfaces.space/) | `fetch` | Loading screens only, with an academic taxonomy | `/the-taxonomy/`, per-game pages | Static since 2023 |
| [Flomob](https://www.flomob.com/) | `links` | Mobile games only; 104 screen categories (season pass, rewards, inventory…) | `/discover-screens/category/<slug>-<id>`, e.g. `season-pass-67` | Full gallery needs sign-up; terms bar "automated tools (bots, scrapers, crawlers) without consent" |
| [GameUI.net](https://www.gameui.net/) | `links` | Very large Chinese-language screenshot search | `/games/<id>` | Terms render in JS and were never read |

## 2. App UI and flow libraries — onboarding, paywalls, stores, permission prompts

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [Paywall Screens](https://www.paywallscreens.com/) | `chrome` | Paywalls, including games | `?category=6014&sort=revenue` (6014 = App Store Games) | Free, no login; no restrictive terms |
| [60fps.design](https://60fps.design/) | `chrome` | Interaction videos: rewards, streaks, confetti, gamification | `/shots/filter/<tag>`, `/apps/category/<cat>` | Free tier shows ~6 items per filter. Terms explicitly allow "asking your AI tool to help you understand or recreate an interaction" |
| [Mobbin](https://mobbin.com/) | `links` | The largest app library; `leaderboard`, `achievements-awards`, `game-ui` patterns | `/explore/mobile/screens/<pattern>` | Account and Pro plan; terms bar AI tooling; official MCP server for Pro |
| [Page Flows](https://pageflows.com/) | `links` | Recorded flows, with a Games category | `/<ios\|android\|web>/<products\|flows\|screens>/<slug>/`, e.g. `/ios/products/game/` | Paid |
| [ScreensDesign](https://screensdesign.com/) | `links` | Top-grossing iOS apps, paywalls, flow videos | `/explore/<screens\|flows\|ui-elements>/<slug>/` | Terms bar any "automated means to access the Service" |
| [Adapty Paywall Library](https://adapty.io/paywall-library/) | `links` | ~1,450 game paywalls | `/paywall-library/category/games/` | Terms bar bots |
| [Refero](https://refero.design/) · [Appllama](https://appllama.io/) · [Gummble](https://gummble.com/) | `links` | Web/iOS screens; little game coverage | per site | Paid or login; terms bar automated access or ML use |

## 3. Motion and game feel

No searchable game-feel library exists. Use Game UI Database's `Screen Transitions` and
`Looping Animations` tags (with `vid=1`) and 60fps.design above.

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [easings.net](https://easings.net/) | `fetch` | Naming and comparing easing curves | `#<name>`, e.g. `#easeOutBack` | GPL source |
| [Real Time VFX](https://realtimevfx.com/) | `links` | Game VFX breakdowns and critique | `/tag/<tag>`, `/c/<category>` | Terms bar automated access |

## 4. F2P and monetisation teardowns — why a screen exists, not just how it looks

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [Deconstructor of Fun](https://www.deconstructoroffun.com/blog) | `fetch` | Game deconstructions | `/blog?category=Deconstructions` | Terms bar bulk download and indexing — read a few posts, never sweep |
| [Udonis](https://www.blog.udonis.co/topics/mobile-game-dissections) | `fetch` | Mobile game dissections | `/topics/<slug>` | |
| [Game Developer](https://www.gamedeveloper.com/keyword/deep-dives) | `fetch` | Deep dives and postmortems, some UI/UX | `/keyword/deep-dives`, `/keyword/postmortems` | |
| [Game Economist Consulting](https://www.gameeconomistconsulting.com/blog/) | `fetch` | Economy and pricing design | none | |
| [Naavik](https://naavik.co/category/deep-dives/) | `links` | Business-side deep dives | `/category/deep-dives/` | Terms bar automated access |
| Liquid & Grit · GameRefinery · Sensor Tower Live Ops · Delta Ingest | `links` | Feature and live-ops databases of top-grossing games | inside their apps | Paid or login |

## 5. Accessibility

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [Game Accessibility Guidelines](https://gameaccessibilityguidelines.com/full-list/) | `fetch` | The standard checklist, basic → advanced | `/basic/`, `/intermediate/`, `/advanced/`, `/full-list/`, `?s=<q>` | No use restrictions beyond renaming |
| [Xbox Accessibility Guidelines](https://learn.microsoft.com/en-us/xbox/accessibility/guidelines) | `fetch` | Platform-holder requirements, XAG 101–123 | `/en-us/xbox/accessibility/xbox-accessibility-guidelines/<101-123>` | Personal, non-commercial use |
| [AbleGamers APX](https://accessible.games/accessible-player-experiences/) | `fetch` | 22 design patterns with rationale | `/accessible-player-experiences/access-patterns/<slug>/` | |
| [Can I Play That?](https://caniplaythat.com/category/menu-deep-dives/) | `fetch` | Accessibility reviews; "Menu Deep Dives" | `/category/<slug>/` | |
| [Game Accessibility Nexus](https://www.gameaccessibilitynexus.com/) | `fetch` | Recent accessibility reviews | `/blog/category/reviews/<type>/` | |
| [Gaming Accessibility Database](https://gamingaccessibility.org/) | `fetch` | Which games ship which features — 11k rows | JSON: `wp-admin/admin-ajax.php?action=ninja_tables_dt_public&table_id=82` | CC0. robots.txt asks a 15 s crawl delay |
| [Accessible Games Initiative](https://accessiblegames.com/accessibility-tags/) | `links` | ESA's 24 accessibility tags and their criteria | the index only | Terms bar deep links and robots — link the index, never a tag page |
| [Family Gaming Database](https://www.familygamingdatabase.com/accessibility) | `links` | ~1,400 games assessed feature by feature | `/search/anyfilters/yes/accessibility/<ids>` | Cloudflare; terms unread |

## 6. Platform guidance and other

| Site | Access | Best for | Deep links | Notes |
|---|---|---|---|---|
| [Apple HIG — Designing for games](https://developer.apple.com/design/human-interface-guidelines/designing-for-games) | `fetch` | Touch targets, text minimums, safe areas, controller UI | page is JS; JSON at `developer.apple.com/tutorials/data/design/human-interface-guidelines/designing-for-games.json` | |
| [Gameplay Design Patterns wiki](http://virt10.itu.chalmers.se/index.php/Main_Page) | `fetch` | Named mechanics patterns, 623 pages | `/index.php/<Pattern>`, `/index.php/Category:Patterns` | |
| [game-icons.net](https://game-icons.net/) | `fetch` | 4k+ game icons | `/tags/<tag>.html` | An **asset** source, CC BY 3.0 — using one needs attribution |
| [Fonts In Use — video games](https://fontsinuse.com/tags/672/video-games) | `links` | Typography in shipped games | `/tags/672/video-games` | Terms bar robots and data mining |
| [The Spriters Resource](https://www.spriters-resource.com/) | `links` | Ripped UI sheets, to see how a game's UI is sliced | `/<platform>/<game>/` | Ripped assets; terms bar commercial use |
| [MobyGames](https://www.mobygames.com/) | `links` | Screenshots by game and platform | per game | Terms bar LLM grounding and RAG use by name |

## Dead or dormant — do not suggest

Screenlane and UI Movement (→ Page Flows), UI Sources and Scrnshts (→ ScreensDesign),
Playliner (→ Sensor Tower), Mobile Free To Play (no posts since 2020), Pttrns,
mobile-patterns.com, uxfind, UIguana, UX Archive, Patterna, gamefeel.com,
gamejuice.co.uk, dagersystem.com, gameuxmasterguide.com, Game UX Library,
gamegui.net, game-patterns.com, gamesui.com.
