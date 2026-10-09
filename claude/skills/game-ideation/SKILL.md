---
description: Run an interactive game-concept session. It asks how hands-on to be, starts from where the idea is (nothing, a one-line pitch, a written concept, a prototype), then works through fantasy, three concept cards, a nested core loop, twist and comps, pillars with design tests, scope and forcing questions, and ends with a one-page concept as a local HTML page plus one concrete next test. Use when the user wants to brainstorm, shape or stress-test a game idea, asks what game to make, or has a pitch or design doc to challenge. Not for UI references (game-ui-refs) or building the game (gamedev).
argument-hint: [genre, theme or one-line pitch | open]
allowed-tools: AskUserQuestion, Read, Write, Edit, Bash, Glob, Grep, WebSearch, ToolSearch
---

# game-ideation

Turn a game idea into a concept that has been argued with: a fantasy, a loop, a twist, pillars,
an honest scope and one test that can kill it. `$ARGUMENTS` is a genre, theme or pitch; `open`
or nothing means start from zero.

Output is a concept page, never code. The agent is a facilitator and a sparring partner: the
concept is the user's, so every direction choice is theirs.

## Asking

- **Choices** go through AskUserQuestion, one self-contained question per decision: the facts
  it turns on inside the question, one line of substance per option, the recommendation first
  and marked `(Recommended)`.
- **Open probes** (the fantasy, a forcing question, "what is the twist") are asked as one
  plain-text question; end the turn and wait. Never fit an open answer into option buttons.
- If AskUserQuestion is not callable, load it with ToolSearch `select:AskUserQuestion`.

## 0. Start

Read the repo's `CLAUDE.md` and any earlier concept first: Glob `docs/*concept*` in the repo and
`*game-concept*.html` in `${DEV_ROOT:?run agents-shared/scripts/init-global.sh}/notebook`. If one
exists, read it and ask whether to refine it or start fresh.

Then one AskUserQuestion call with two questions:

**How hands-on?** Sets the mode for the whole session.

| Mode | What it means |
|---|---|
| Guided (Recommended) | One question at a time. Each phase ends with what was decided, and the user confirms before the next. |
| Brisk | Related questions batched, up to four in one call. Only the three routed forcing questions. Confirmation at the concept pick and before writing the page. |
| You drive | Ask only for a one-sentence brief, platform, team and scope, and the pick among three concepts. Draft every other phase. The page marks each drafted field `drafted, not challenged` and lists the unasked forcing questions. |

**Where is the idea?** Sets the maturity level, which sets the entry phase and the questions.

| Answer | Level | Start at | Forcing questions |
|---|---|---|---|
| Nothing yet | 0 | 1 Fantasy | Q1, Q3, Q5 |
| A one-line pitch | 1 | 3 Loop | Q2, Q3, Q4 |
| A written concept or design doc | 2 | 4 Twist | Q2, Q5, Q6 |
| A prototype or playtest data | 3 | 8 Forcing questions | Q1, Q4, Q6 |

At level 3 ask once whether it is a prototype nobody else has played, or one with playtest
notes; the second skips Q6 and reads the notes instead.

## 1. Fantasy

The question is what the player gets to feel or be, never which features exist.

Work backward from the feeling: **aesthetic** (sensation, fantasy, narrative, challenge,
fellowship, discovery, expression, submission), then the **dynamics** that produce it, then the
**mechanics** that allow them. Stuck? Ask for a moment in any game when they lost track of time
and what caused it, or ask them to finish "I want the player to feel ___ when they ___".

A feature list is not a fantasy. Say so and ask for the feeling: "That is what the player does.
What do they feel while doing it?" Keep pushing until the answer is a feeling.

Read it back as one sentence, with its dominant aesthetic and the player behaviours it implies,
and get confirmation. Every later phase has to trace back to this sentence.

## 2. Landscape check (optional)

Ask first. One AskUserQuestion, with the number and shape of the requests in the question:

- **Search** (Recommended): 2 or 3 web searches in standard mode, generic terms only, such as
  "<genre> games <year>" and "<core mechanic> <genre> market". Never the concept's name or
  anything proprietary.
- **Skip**: work from what the model already knows, and say the page has no market evidence.

On a 429, a consent wall or any refusal, stop searching and carry on without it.

Synthesise three layers: what everyone in the genre already does, what the results show is
crowded or missing, and whether this fantasy stands apart or is "zombie survival number 47".
Name a eureka only when an assumption the whole genre makes looks wrong, with the evidence.

## 3. Three concepts (levels 0 and 1; also on request at 2)

Generate three concepts, each from a different technique, so they differ in kind:

- **Verb-first**: the most repeated action is the game; build outward from making it feel good.
- **Mashup**: two unrelated genres or mechanics; the tension between them is the hook.
- **Experience-first**: start from the target aesthetic and derive dynamics, then mechanics.

Each concept is one card: working title, two-sentence pitch, core verb, fantasy, hook ("like X,
and also Y", where the "also" must change play, not only look), dominant aesthetic, scope
(small, medium, large), why it could work, biggest risk.

The user picks one, combines, or asks for fresh directions. For a level 1 pitch, one card
should be the pitch itself, so the other two measure it.

When the user is stuck or wants more raw ideas, offer a deepener from
`references/techniques.md` (relative to this skill's directory). Offer two or three that fit,
never the whole list, and run the one chosen with its prompts.

## 4. Core loop

Write the loop as one sentence: **verb, feedback, reward, repeat**. If it takes a paragraph it
is several loops or a session description; as a working heuristic, more than five or six verbs
means it is not distilled yet.

Then nest it, one level at a time:

- **30 seconds**: what the hands do most. Is it satisfying with no reward, progression or
  story? "Shooting in Hades feels good with nothing attached." If the user cannot say it in
  fifteen seconds the concept needs work.
- **5 minutes**: what structures the 30-second action into cycles; where "one more run" starts;
  which choices live here.
- **A session**: a natural stopping point **and** a reason to return. Both are required.

**Verb test**: is the verb worth doing for itself, or only for the reward? If only for the
reward, the loop is hollow; offer to look for a different core action.

## 5. Twist and comps

The twist has to live in the mechanics, since theme and art are easy to copy. Apply the
**screenshot test**: would one screenshot show the difference from the closest competitor?

**Comp set**: three nearest games. For each, what it does that this also does, what it lacks
that this provides, and what it does that this deliberately avoids. If the user cannot name
three, either they do not know the genre (send them to play three and come back) or the idea is
genuinely new, which is rare, so probe harder.

State the twist in one sentence. Then show the concept so far (fantasy, loop, twist, closest
comp) and ask: lock it in, explore alternatives (back to 3), or adjust one part.

## 6. Pillars

Three to five pillars, as a working range. Each has a name, a one-sentence definition and a
**design test**: "when we are debating X versus Y, this pillar says choose ___". Each must be
**testable** (a prototype could check it) and **actionable** ("fun" is neither; "tense survival
under resource pressure" is). Pillars that never pull against each other are not doing work, so
name at least one real tension.

Then three or more **anti-pillars**: what this game refuses to be. Each "no" protects a "yes".

## 7. Player and scope

- **Who it is for, who it is not for.** Use player-type and motivation models (Bartle,
  self-determination) as lenses to prompt the answer, not as evidence.
- **Platform and session length.**
- **Team and time.** Ask what the user actually has; never assume a team size or hours.
- **Two scope numbers**: the full vision and the smallest version that tests the core loop, in
  person-months or the user's own unit. A ratio above about ten to one means the full vision is
  a fantasy; start from the small one.
- **Hardest unknown**: the one technical or design question with no answer yet, and whether the
  user has done anything like it.

## 8. Forcing questions

Ask the routed three from the level table, one at a time, as open probes. After each answer
push once more, because the first answer is the polished one. Do not soften them.

| # | Ask | Push until | Red flag |
|---|---|---|---|
| Q1 | Describe the fun. Have you seen it, or imagined it? | An honest label: observed or imagined. Imagined fun is a hypothesis. | "Everyone I told says it sounds fun." That is interest, not play. |
| Q2 | Name three games most like this. What does each lack that yours provides? | Three titles and three specific gaps. | "Nothing is like this." |
| Q3 | Explain one complete session in thirty seconds. | A sequence a non-gamer could follow, for the main mode. | "It depends on the mode." |
| Q4 | First play versus hundredth: what changed? | A concrete change: new strategies, deeper mastery, social dynamics. | "Bigger numbers." That is a treadmill. |
| Q5 | Full vision versus smallest fun version: how many person-months each? | Two numbers. | "I have not thought about scope," which is fine at level 0 and not at level 2. |
| Q6 | Have you watched anyone play it, controls handed over, saying nothing? | One specific observation. | A demo, or a survey. |

If the user pushes back with "just brainstorm": the first time, say these questions are the
brainstorming and ask two more; the second time, respect it and list the skipped ones on the
page.

## 9. The next test

Every session ends with one assignment the user can start today, never "go build it":

- Level 0 or 1: show a five-slide pitch or a one-paragraph pitch to five people in the target
  audience, and watch whether they ask when they can play.
- Level 2: a paper prototype of the core loop, or a 48 to 72 hour greybox; a digital greybox can
  start from `/gamedev:prototype-fast`.
- Level 3: a blind playtest: hand over the controls, say nothing, write down where they stall,
  quit or replay.

Write the **pass or fail line** with it: the observable result that means the loop works, and
the one that means stop.

## 10. Write the page

Pick the sections from the table below and scaffold with `project-lifecycle page-new`, as
`/new-html-page` describes: `--title` two to four words (the game's working title), one
`--section` per heading, `--repo` the repo the game belongs to (or `notebook`),
`--session` this session's id, `--out` the file.

Where it goes: `docs/<date>-game-concept-<slug>.html` in the game's repo when the session runs in one;
otherwise `$DEV_ROOT/notebook/<date>-game-concept-<slug>.html`. A concept page is something the
user will open, so it lives in a repo, never in the scratchpad.

| Section | Holds |
|---|---|
| Fantasy | The one sentence, dominant aesthetic, implied behaviours |
| Core loop | The one-sentence loop, the three nested levels, the verb-test result |
| Twist and comps | The twist, the three comps with the gap each leaves |
| Pillars | Each pillar with its design test, the tension, the anti-pillars |
| Player and scope | Audience and non-audience, platform, session length, the two scope numbers |
| Risks and open questions | Biggest risk, hardest unknown, each forcing question with the answer, skipped ones named; every claim labelled observed or imagined |
| Next test | The assignment and its pass or fail line |

Fill them with semantic HTML only. Then render and read the page as `/new-html-page` step 4
says, and hand over the absolute path on its own line. Do not publish it.

## Rules

- **No praise.** Never "great idea" or "players will love this". Acknowledge a narrowing by
  saying what it fixed: "Going from 'RPG' to 'solo RPG about time loops' fixes the scope and
  sharpens the hook".
- **Say the hard thing first**, then the reason. Name the failure pattern when you see one.
- **Concrete over vague.** Replace "engaging", "immersive" and "balanced" with the mechanic and
  the feeling it causes.
- **Concepts are the user's.** Offer, recommend, never decide a direction for them.
- **Stuck three times** on the core fun: send them to play three competitors and return with
  notes. **Contradicting itself after two rewrites:** stop ideating and paper-prototype.
- **No telemetry, no state outside the page**; the session writes one file.

## Provenance

The structure is new; the ideas come from MIT-licensed skills and a couple of unlicensed ones,
and none of their text is copied. Maturity entry, forcing questions and the push-back posture
follow gstack-game's game-ideation. The three generation techniques, loop levels, pillars with
design tests and anti-pillars follow Donchitos' Claude-Code-Game-Studios brainstorm. The
technique deepeners follow BMAD game-dev-studio's technique table. The testable-and-actionable
pillar check and loop distillation follow rbergman's game-vision. The thresholds in this skill
(five or six verbs, three to five pillars, ten to one) are rules of thumb from those sources, not
measured figures.
