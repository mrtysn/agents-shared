---
description: Triage Claude Code sessions across open iTerm2 tabs after a relaunch — which are live, which were killed by the restart, which tabs moved on. Offers resume one-liners, per-session summaries, and handoff prompts for finishing leftover work in a fresh session. Covers all claude config dirs. iTerm2-only.
user-invocable: true
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep, Agent
argument-hint: [table | resume | summarize | handoff] [optional tab/session filter, e.g. t11]
---

# iterm-revive

Walks every open iTerm2 tab (read-only — no focus steal, no keystrokes), extracts Claude Code session UUIDs from tab text, and classifies each tab by cross-referencing running claude processes (by tty) and transcript mtimes against iTerm2's own start time. Transcripts are indexed across every claude config dir (`~/.claude*` with a `projects/` subdir, plus any `CLAUDE_CONFIG_DIR` found in a running claude process's environment).

**Mode** is the first word of `$ARGUMENTS` (default `table`). An optional second token filters to one tab (`t11`, `w1.t11`) or a session id prefix.

## table (default)

```bash
python3 ~/dev/personal/agents-shared/scripts/iterm-revive.py
```

Print the output as-is. Buckets: `LIVE` (claude process on the tab's tty), `ENDED BY RESTART` (the ones worth reviving), `MOVED ON` (session exited normally or the tab was reused for other work — deliberately skipped), `UNRESOLVED` (claude-flavored tab name but the UUID scrolled off the visible screen).

## resume

```bash
python3 ~/dev/personal/agents-shared/scripts/iterm-revive.py resume
```

Emits one `cd <cwd> && claude --resume <uuid>` line per ended session, cwd taken from the session's own transcript. Sessions from a non-default config dir get a `CLAUDE_CONFIG_DIR=<dir>` prefix. Print them verbatim in a code block — complete and copy-pasteable, never abbreviated.

## summarize

Run the script with `json`, then for each `ended` session spawn parallel subagents (one per session, single message, multiple Agent calls). Each subagent reads the tail of that session's `transcript` path (last ~200 lines of the jsonl) and returns: one-line goal, completion state (finished / awaiting user decision / died mid-turn), and the outstanding next step if any. Render one table row per session: tab, project, one-liner, state, outstanding.

## handoff

Same json + subagent fan-out as summarize (honor the filter argument — usually one session), but each subagent returns a paste-ready handoff block:

- cwd and branch to start in
- goal of the session (from the last recap / opening prompt)
- what was completed
- the outstanding work, concrete enough to act on
- files touched in the final turns

Output the block(s) as text for the user to paste into a fresh session. Never write them to a file. Recommend `resume` instead when the leftover work needs deep accumulated context, and `handoff` when the transcript was near its context limit (large jsonl, `/clear` suggestions in the tail).

## Known limitations

- AppleScript exposes only the visible screen per tab, not scrollback. Dead sessions whose UUID scrolled off land in `UNRESOLVED` — cross-check those with `/recent-sessions`, or scroll the tab up and re-run. Full-scrollback support would require iTerm2's Python API (Settings → API), not currently used.
- Live sessions with no on-screen UUID and no `--resume` in argv are matched by project-name heuristic and may show `?` — the process is confirmed alive either way.
- The moved-on filter is heuristic (post-restart transcript mtime, or typed commands after the last claude block). When in doubt a session lands in `ENDED` rather than being silently skipped.
