---
description: Write a pitch for a game, product or project, fitted to who will hear it. It asks the mode (lines only, a full set of scripts, rehearsal against a simulated listener, or sharpening a pitch the user already has), the target (players or kids, customers, investors, a collaborator or publisher), how it is delivered and whether there is something to show. Every pitch passes the two-sentence test with a blind sub-agent, a jargon and "X for Y" check, and a scored rubric, and ends as a local HTML page in the repo plus one test with real listeners. Use when the user wants a pitch, an elevator pitch, a one-liner, a tagline, a store-page blurb, a publisher or investor pitch, or wants to practise or sharpen one. Not for shaping the idea itself (game-ideation).
argument-hint: [what the pitch is about | path to an existing pitch]
allowed-tools: AskUserQuestion, Agent, Read, Write, Edit, Bash, Glob, Grep, ToolSearch
---

# write-pitch

Say what a thing is so that the person hearing it understands it, remembers it and knows what to
do next. `$ARGUMENTS` names the thing or the path of a pitch the user already has; nothing means
the repo the session runs in.

The agent writes and argues; the facts are the user's. A pitch never claims anything the user has
not said or the repo does not show.

## Asking

- **Choices** go through AskUserQuestion, one self-contained question per decision: the facts it
  turns on inside the question, one line of substance per option, the recommendation first and
  marked `(Recommended)`.
- **Open probes** (the one moment that sells it, what the listener should do after) are asked as
  one plain-text question; end the turn and wait. Never fit an open answer into option buttons.
- If AskUserQuestion is not callable, load it with ToolSearch `select:AskUserQuestion`.

## Sub-agents

Each sub-agent gets a brief that stands alone and names the repo path of anything it hands back.
Size each by the house table the Agent hook prints on a session's first spawn:

| Sub-agent | Does | `model` | `effort` |
|---|---|---|---|
| Material | Reads the repo's README, `CLAUDE.md`, `docs/`, concept and earlier pitch pages, and lists the facts a pitch can use, each with its file | haiku | low |
| Cold reader | Gets only the two sentences and the example, nothing else, and paraphrases them back (step 4) | haiku | low |
| Cold listener | Gets only a script and the listener's role, and says where it tuned out and what it would ask (step 7) | sonnet | medium |

Scoring stays in the main session: it needs the whole conversation. Run the material sub-agent
only when the repo has more than a handful of documents; otherwise read them directly.

## 0. Start

Read the repo's `CLAUDE.md`, then look for material: Glob `docs/*concept*`, `docs/*pitch*` and
the README. A concept page from `/game-ideation` holds the fantasy, loop and twist, which are most
of a player pitch. If an earlier pitch page exists, read it and ask whether to refine it or start
fresh.

Then one AskUserQuestion call with these four questions. The option marked `(Recommended)`
below is the default; when the material points to another (a repo with a playable build and no
company behind it: Players and A playable build; a pitch deck in `docs/`: Investors and Slides),
move that one first and mark it instead.

**What should this session produce?** Sets the mode.

| Option | What it means |
|---|---|
| Lines (Recommended) | The two sentences and example, an elevator pitch of 50 to 75 words, one-liners per channel and tagline candidates. The fastest way to find out whether the thing can be said at all. |
| Full set | The lines plus spoken scripts at the lengths this listener gets, questions they will ask with honest answers, and for investors an email and a deck outline. |
| Rehearse | The lines and the script for one length, then the user delivers it to a simulated listener who asks what a real one would and pushes on the weak points, then feedback out of character. |
| Sharpen mine | The user already has a pitch. Run every check on it, score it, and rewrite only the parts that fail. |

**Who will hear it?** Sets the target, which decides what goes in (the table in step 2).

| Option | What it means |
|---|---|
| Players or kids (Recommended) | The people who would play it. Leads with the moment of play; no market, money or tech talk. |
| Customers or buyers | People who would pay for it or use it at work. Leads with the problem they have today and what changes. |
| Investors | People who would fund it. Keeps traction, market, model, team and the ask. |
| A collaborator or publisher | Someone who would build, fund-and-ship or distribute it with you. Leads with what is proven and what you need from them. |

Other covers anyone else; then ask in plain text who they are and what they should do after
hearing it.

**How will it be delivered?** Sets length and form.

| Option | What it means |
|---|---|
| Said aloud (Recommended) | In person or on a call. Short sentences, written to be spoken; scripts are word for word with where to pause. |
| Written | A store page, an email, a post or a README. Read in seconds, so the first line carries it. |
| Video or trailer | A voiceover over footage. Lines are timed to what is on screen. |
| Slides | A deck. Each slide's headline states its point; the headlines alone must make the pitch. |

**Is there something to show?** Decides whether the pitch points at a demo or has to paint it.

| Option | What it means |
|---|---|
| A playable build or live product (Recommended) | The pitch hands over the controls as early as it can; words set up the moment, the build delivers it. |
| Screenshots or video | The pitch names what is on screen as it goes and refers to it, never describes around it. |
| Nothing yet | The pitch carries the moment in words alone, so the concrete example has to be vivid, and every claim about how it plays is marked imagined. |

## 1. The facts

Collect, from the material and then from the user, only what the target and mode need (the
"Keep" column of step 2). Ask what is missing in one plain-text message, at most five items.

Label every fact **observed** (seen, measured, played by someone else), **estimated** (a number
with its method) or **imagined** (what the user expects). The label travels with the fact to the
page. No fact is invented to fill a slot; a missing one is left out and named under Risks.

Then one open probe, always: **"What is the single moment, for one specific person, that shows
why this matters?"** For players it is a moment of play; for a customer, the hour their problem
went away; for an investor, the example that makes the two sentences impossible to misread.

## 2. The listener

The target changes the content, not only the tone.

| Target | Lead with | Keep | Leave out | "X for Y" | Ends with |
|---|---|---|---|---|---|
| Players or kids | The moment of play: what your hands do and what happens next | The verb, the feeling, one concrete moment, where and how to play | Market, money, tech, genre labels, the word "innovative" | Only with a game this player has played: "like X, but Y" | "Play it": a link, a code, the build handed over |
| Customers or buyers | The problem they have today, in their words | What changes for them, how it differs from what they use now, price or how to get it | Fundraising, market size, team bios | Only with a product they use | A next step they can take today: try, book, buy |
| Investors | What it does, then the strongest proof (traction, team or insight, whichever is strongest) | Traction with timeframes, the non-obvious insight, bottom-up market math, one business model, team accomplishments, why now if it is real, the ask | Feature lists, unexplained jargon, a top-down market number | Only with a company every investor knows, and only as a hook | The ask: amount, the milestones it buys, the timeframe |
| A collaborator or publisher | What it is and what is already proven: a build, a playtest, a number | Scope and timeline, what you need from them, what they get, why you can ship it | Market-size theatre, the fundraising ask | Only with a title they know in their catalogue or genre | A specific request: a call, a build review, a term |
| Other | Whatever this listener cares about first; ask | What lets them act | Whatever they cannot use | Only if X is theirs | The one thing they should do next |

Pick the order of the rest by what is strongest for this listener: for investors, the lead
element after the two sentences is whichever of traction, team, insight or market is most
impressive; with none of them, the problem and the insight.

## 3. Two sentences

Write what it is in exactly two sentences plus one concrete example. Sentence one says what it
is, sentence two how it works or who it is for, and the example makes it impossible to misread.

> Weak: "An innovative physics-driven social sandbox experience leveraging emergent gameplay."
> Better: "You and your friends each steer one leg of the same giant robot. It only walks when
> you agree; last night four kids took twenty minutes to cross a river and screamed when it fell
> in."

Write it for the target: the player version names the moment, the investor version names the
business. Everything else in the pitch is built on these two sentences, so settle them before
moving on.

## 4. Checks

Run all three on the two sentences, and again on every line and script before it goes on the page.

**Two-sentence test (cold reader).** Start the cold-reader sub-agent with only the two sentences,
the example and the target's role: "You are <a 10-year-old player | a buyer | an investor | a
publisher>. You know nothing else about this. In your own words: what is it, who is it for, what
would you do next? Then list every word you would not understand or would have to guess." Compare
its paraphrase with what the user means. A wrong or vague paraphrase means rewrite; never argue
with the reader.

**Jargon.** Flag every word the target would not use themselves: acronyms, genre labels, "leverage",
"platform", "seamless", "immersive", "engaging", "AI-powered", "innovative", "next-generation". Replace
each with the concrete thing it stands for. For players, aim for words a ten-year-old uses.

**"X for Y".** Allowed only when the target knows X well, the analogy sets the right expectations,
and the pitch still works with it removed. Kids know Roblox, Minecraft and Fortnite, not Uber;
investors know Uber, not a niche indie hit. When it fails any of the three, cut it.

## 5. Lines (every mode)

- **Two sentences and the example**, from step 3.
- **Elevator pitch**: 50 to 75 words, about thirty seconds aloud: what it is, who it is for, why
  they should care, and the ending from the step 2 table.
- **One-liners per channel** the target meets it in, each one line: a store page or README first
  line, a social bio or post, a spoken introduction, and a trailer end card for games.
- **Taglines**: three candidates, each with its **possible misread** (what someone could wrongly
  take from it). Drop any whose misread is likely.
- **Only statement** (customers, investors, collaborators): "<It> is the only <category> that
  <difference> for <who> who <need>." If "only" is a stretch, the difference is not yet real; say
  so and name it under Risks rather than writing a false one.

## 6. Scripts (Full set and Rehearse)

Lengths by target; Rehearse writes only the one the user picks.

| Target | Lengths |
|---|---|
| Players or kids | 30 seconds, 1 minute |
| Customers or buyers | 30 seconds, 2 minutes |
| Investors | 1, 2, 5 and 10 minutes, an email, a deck outline |
| A collaborator or publisher | 1, 2 and 5 minutes, an email |

A script is word for word, with the two sentences first and the lead element right after them.
Show, never tell: describe what the listener would see and do ("you tap, the bridge folds, your
friend falls in"), never what the feature is. Mark where to pause and where to hand over a demo
when there is one. Every number has a timeframe; every market figure shows its multiplication.

A deck outline is a list of slides whose headlines state the point ("Kids replay a level eleven
times on average", never "Retention"); the headlines read in order must make the pitch.

**Questions to expect**: the five to ten questions this target will ask, each with an honest answer;
weaknesses named, each with what is being done about it. "We do not know yet; here is how we will
find out" is a valid answer and better than a made-up one.

## 7. Rehearse

1. Start the cold-listener sub-agent with only the script and a persona that fits the target:
   a player of the right age who has three other games open, a buyer comparing with what they use,
   an angel (asks "why you"), a seed investor (asks for numbers and growth), a publisher (asks
   what is proven and what it costs them). It returns where it tuned out and the questions it would
   ask, in order.
2. Ask the user to deliver the pitch in plain text, or to say it aloud and paste what they said.
3. In character, ask the cold listener's questions one at a time, three to five of them, each as a
   plain-text question. Push once on any weak answer; a real listener does. Do not coach in
   character.
4. Out of character: what landed, where the listener would have stopped listening, which answers
   were strong and which were not, and the one change that would help most. Offer another round
   with a different persona.

## 8. Score

Score the pitch against the rubric, honestly; a high score on a weak pitch helps nobody. Each
dimension is 1 to 5.

| Dimension | 5 means |
|---|---|
| Clarity | The cold reader's paraphrase matched what the user means |
| Concreteness | It has one specific moment or example, not a category |
| Strength first | The strongest thing for this listener is in the first fifteen seconds |
| Fit | Nothing from the "Leave out" column is in it, and everything in "Keep" that exists is |
| Plain words | No flagged jargon left; any "X for Y" passes the three conditions |
| Honesty | Every claim is labelled; numbers carry timeframes; nothing imagined is said as observed |
| Next step | The listener knows exactly what to do after hearing it |

Total out of 35. As a rule of thumb: 30 or more, go and say it; 22 to 29, fix every dimension
under 4 first; under 22, go back to the two sentences. For each dimension under 4, write what is
weak and one specific fix, then ask whether to apply the fixes and re-score.

## 9. The next test

Every session ends with one test the user can run this week with real people, never "go pitch":

- Players or kids: say the 30-second pitch to three to five players of the target age and ask
  them to tell a friend what it is. Pass: they say the moment back and ask to play. Fail: they
  repeat the genre, or ask what it is.
- Customers: send the elevator pitch to three people who have the problem. Pass: one asks how to
  try it. Fail: they ask what it does.
- Investors or publishers: say the two sentences to two people outside the field and ask them to
  explain it back, then give the 2-minute script to one friendly person in the field. Pass: both
  paraphrases match, and the insider asks about the insight or the numbers, not about what it is.

## 10. Write the page

Scaffold with `project-lifecycle page-new`, as `/new-html-page` describes: `--mode report`,
`--title` two to four words (the thing's name and "pitch"), one `--section` per heading below that
has content, `--repo` the repo the pitch is about, `--session` this session's id, `--out` the file.

Where it goes: `docs/<date>-pitch-<target>-<slug>.html` in the repo the pitch is about; with no
repo, `${DEV_ROOT:?run agents-shared/scripts/init-global.sh}/notebook/<date>-pitch-<target>-<slug>.html`.
The user will open it, so it lives in a repo, never in the scratchpad. Starting the page is
mechanical once the content is settled; write it in the main session, or hand the finished
content to a sonnet sub-agent at medium effort.

| Section | Holds |
|---|---|
| Two sentences | The two sentences, the example, the target and how it is delivered |
| Lines | Elevator pitch, one-liners per channel, taglines with their misreads, the only statement |
| Scripts | Each length word for word, the email, the deck outline (Full set and Rehearse) |
| Questions | The questions to expect with answers and the named weaknesses |
| Rehearsal | Each round's persona, questions, what landed and what did not (Rehearse) |
| Checks and score | The cold reader's paraphrase verbatim, jargon flagged and replaced, the "X for Y" verdict, the rubric table with total and fixes |
| Risks | Missing facts, imagined claims the pitch rests on, an "only" that does not hold yet |
| Next test | The test and its pass and fail lines |

When refining an earlier pitch page, open the new page with `Supersedes: <path of the earlier page>`.
Fill with semantic HTML only, render and read it as `/new-html-page` step 5 says, and hand over
the absolute path on its own line. Do not publish it.

## Rules

- **No praise.** Never "great hook" or "investors will love this". Say what a change fixed.
- **Say the weak part first**, then why. A pitch with no proof says so rather than borrowing
  confidence it has not earned.
- **Concrete over impressive.** Replace every adjective with the thing it describes.
- **Nothing invented.** No metric, quote, user count or market figure the user did not supply; a
  placeholder is written as `[needs: …]` and listed under Risks.
- **One pitch per listener.** A pitch for two targets at once is two pitches; ask which comes first.
- **No network**: the pitch is built from the user's material, never from searches about the
  market or the listener.
- **No state outside the page**; the session writes one file.

## Provenance

The structure is new; the ideas come from three MIT-licensed sources, adapted into this repo's
wording with none of their text reused:

- startup-pitch, from ferdinandobons/startup-skill: the two sentences plus one example and the
  explain-it-back test, lead with what is strongest, show rather than tell, timeframed traction and
  bottom-up market math, scripts by length, the deck headline rule, questions to expect, the scored
  rubric (here rescaled to seven dimensions of 1 to 5 and made audience-neutral) and the investor
  roleplay, which became the rehearse mode.
- startup-positioning, from the same repo: the one-liners per channel, tagline candidates with a
  possible misread, and the only statement from Neumeier's onliness test; Moore's template is folded
  into it.
- sales-get-marketing, from nasrulhazim/claude-sales: the 50 to 75 word elevator pitch that ends
  with what to do next.

New here: the target table, the four opening questions, the cold-reader and cold-listener
sub-agents, the observed / estimated / imagined labels (shared with `/game-ideation`) and the
next test with real listeners. The word counts and score bands are rules of thumb from those
sources, not measured figures.
