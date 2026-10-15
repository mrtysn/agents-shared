# Choose the fix for a repeated pattern

The one table of where an instruction or a fix goes. It is shown once per session, by
`hooks/show-rule-at-action.sh`, the first time a session writes a rule, a skill, a hook
script, a trigger row, an on-demand doc or a `CLAUDE.md`. It is also read by
`docs/MAINTAINING-RULES.md` when a new rule arrives, by `pattern-discovery-for-new-skill`
when it writes its verdict, and by `vet-fable` when the subject under review is which fix
to build. It lives here, not in `claude/rules/`, so no session pays for it at launch.

## First: does a fix already exist, and why did it not fire?

A pattern that repeats while something covers it is almost never fixed by writing a
second thing. Find out why the first did not work:

| What the evidence shows | Fix |
|---|---|
| Agents never knew the tool, rule or script existed | a trigger row or hook at the moment it applies |
| It exists but loads too late, or only at launch and gets ignored | move it to the moment of action (trigger row) |
| It fires and agents follow it, but it is too vague to act on | make it specific; specificity, not volume, is what changes behaviour |
| It exists and fires, and agents follow it, but it is wrong | edit it |
| Nothing covers it | choose from the table below |

## The table

| Situation | Fix | Cost |
|---|---|---|
| A fact with no repo home | memory entry | loads by index line; one per fact |
| Guidance every session needs whatever it is doing | rule in `claude/rules/` | loaded at launch, everywhere, so **every session pays for it**; keep a short core and put the full text on demand |
| Relevant to one project only | that repo's `CLAUDE.md` | loaded when working in that repo |
| Relevant only when working with certain files | that repo's `.claude/rules/` with `paths:` frontmatter | loads on a file match, which saves context |
| Machine-specific, private, or a path | a gitignored local file | `agents-shared` is **public** |
| A rule that matters only at a tool call | trigger row in `hooks/rule-triggers.tsv` plus a doc at `docs/on-demand/<id>.md` | `deny-once` fires before the action, `note-once` alongside it; **tool calls only** (PreToolUse), matched on `command`, `file_path`, `content` or `url` |
| Something that must run at a fixed moment unconditionally (rules are context, not enforcement), the moment is not a tool call, or the check needs its own logic | hook, wired by hand into `settings.json` and listed in the README | `nudge-transcript-parsers.sh` is a worked example of a check with state; the system-one repo's `system-one-prompt.sh` sees a typed prompt and `system-one-stop.sh` the final message |
| Steps worth fixing that someone invokes: a brief to write, a model to pick, a way to read a result | skill | does nothing unless invoked, so its description has to carry the phrases that call it; **every skill's description loads into every session's prompt** |
| A repeatable computation or search | script in `scripts/`, per [persist useful tooling](persist-useful-tooling.md) | an agent has to know it exists, so give it a trigger row or a rule line |
| The fix needs state across events, rewriting content, or drawing | mod (**untested here**) | see below |

## Mods

A mod does everything a shell hook does (deny or rewrite a tool call, rewrite a
prompt) and also keeps state across events, runs timers, calls a model, and draws UI:
a pane, a band above the prompt, a status line, a slash command that drives the
interface. Take a shell hook when stdin to an exit code is enough; take a mod only
when that is not.

- Installed with `claude --plugin-dir <folder>`, `CLAUDE_CODE_PLUGIN_DIRS`, or a
  marketplace, **not** by `scripts/init-global.sh`, so a mod carries setup that a
  hook does not. A mod a session writes for itself is hot-reloaded from that session's
  mods folder once the user enables it.
- Written against the `plugin-authoring` skill of Claude Code 2.1.299, and not yet
  tried here. Check that skill's types for the running version before promising what
  one can do.

## By kind of pattern

- **A repeated agent failure** is a trip that recurred. Start from
  [fix what tripped you](../../claude/rules/fix-what-tripped-you-at-its-source.md) for
  where the fix goes (a guard, then an error message, then a doc line, then memory),
  and use this table only for the mechanism.
- **A repeated request** earns a skill when the steps are worth fixing, a script when
  the work is a computation, and nothing when each instance needs different judgment.
- **A tone cue** is not a fix. Find what provoked the mood, and fix that failure.
- **A tool or feature under consideration** is measured by the moments it would have
  helped. The verdict is adopt or not, and for adoption, the row above that makes
  agents reach for it.

## Provenance

Oct 14 2026: three runs of `pattern-discovery-for-new-skill` ended in a verdict worded
"skill or rule". The chat-log run's own finding was that agents did not know the shared
reader existed, which a trigger or hook fixes and a skill does not. Another ended
"neither" with "enforce the existing rules" and no word for how. A third was a
tool-adoption question, not a pattern.
