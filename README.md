# agents-shared

Shared Claude Code behavioural rules, skills, and commands — installed machine-wide
via `~/.claude/` symlinks, reaching every project on the machine.

**Maintaining this across several machines:** see
[docs/MAINTAINING-RULES.md](docs/MAINTAINING-RULES.md) — new-machine setup, keeping
machines in sync, and where a new rule belongs versus a skill, a project CLAUDE.md, or a
hook.

## Usage

### Install globally (one machine, every project)

Symlink everything into the user-level Claude dirs (`~/.claude/commands`,
`~/.claude/skills`, `~/.claude/rules`) so every project on the machine sees
these commands, skills, and rules:

```bash
bash scripts/init-global.sh           # sync ~/.claude with this repo
bash scripts/init-global.sh --unlink  # remove the symlinks it created
```

Idempotent — re-run after adding, renaming, or removing a command/skill. New
sources are linked, wrong-target links repaired, orphaned links (renamed/deleted
upstream) pruned, and real local override files left untouched. Honors
`CLAUDE_CONFIG_DIR` if set.

### Profiles: personal and work

Each Claude config folder declares its profile in its own `paths.local.sh`, which is
never synced:

```bash
AGENT_PROFILE=personal     # or AGENT_PROFILE=work; unset means shared content only
```

`init-global.sh` reads it through `scripts/agent-profile` and links
`claude/rules/personal/` and `claude/skills/personal/` only on the personal profile; on
any other it removes links of its own into them. A machine with several config folders
runs the installer once per folder: `CLAUDE_CONFIG_DIR=~/.claude-<name> bash
scripts/init-global.sh`. `hooks/show-rule-at-action.sh` shows a doc from
`docs/on-demand/personal/` only on the personal profile; `hooks/personal/` holds the hooks and wording
only the personal profile gets (a stub in `hooks/` keeps a name settings already call). `scripts/check-personal-split.zsh`
(run by `project-lifecycle test`) fails when anything outside the `personal/` folders
names a token from `scripts/personal-only-tokens.txt`; it scans `hooks/` too, except `hooks/tests/`.

### Install local-only (per project, no repo footprint)

Symlink chosen skills from a standalone clone and hide them via
`.git/info/exclude` — no submodule, nothing in git status:

```bash
mkdir -p <repo>/.claude/skills
ln -s <clone>/claude/skills/handoff <repo>/.claude/skills/handoff
echo ".claude/skills/handoff" >> <repo>/.git/info/exclude
```

`git pull` in the clone updates all such repos at once. Exclude links by name,
not all of `.claude/`, so committed skills can coexist. Rarely needed — the
global install already reaches every project. Not automated by the scripts.

## Commands and skills

Not listed here — they are self-describing. Every command (`claude/commands/*.md`)
and skill (`claude/skills/*/SKILL.md`) carries its description in frontmatter,
which is exactly what Claude Code loads into each session. Browse the
directories; skills sourced from third-party repos carry a `source.json`.

Both create `/name` invocations. Skills are directory-based and may carry
references and templates; new extensions go in `claude/skills/`.

## Hooks

Not skills — shell scripts wired by hand into the `settings.json` of the Claude
config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`). `init-global.sh` links every executable
script in `hooks/` into `<config dir>/hooks/`,
so a settings entry can name `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/<name>` and no repo
location; a script finds its siblings from its own folder, symlink resolved.

| Hook | Event | Description |
|------|-------|-------------|
| `hooks/block-tree-discard.sh` | PreToolUse | Refuses git commands that discard uncommitted work; only `git checkout -- <one tracked file>` passes, plus `git switch`/`git checkout <branch>` from a clean tree to an existing local branch with no flags |
| `hooks/block-adb-server-kill.sh` | PreToolUse (`Bash`) | Refuses `adb kill-server`, `killall`/`pkill adb`, and stopping the `local.adb-reconnect.server` launchd agent: a restart drops every device the user holds over wireless adb. A new emulator attaches to the running server by itself; a stuck server is reported to the user, who restarts it from ADB Reconnect. Cases in `hooks/tests/block-adb-server-kill-cases.tsv`, run with `hooks/tests/run-block-adb-server-kill.sh` |
| `hooks/limit-signed-releases.py` | PreToolUse (`Bash`) | Refuses a Firefox add-on signing (`web-ext sign`, a repo's `release.zsh`, AMO's upload API) that addons.mozilla.org would throttle: 3 a minute, 10 an hour, 24 in 24 hours per account. Each signing is appended to `<config>/signed-releases.log` (or `$SIGNED_RELEASE_LOG`); past a limit, the user signs in their own shell. Cases in `hooks/tests/run-limit-signed-releases.sh` |
| `hooks/require-question-facts-in-question.sh` | PreToolUse (`AskUserQuestion`) | Refuses a question whose text points at facts ("above", "the table", "as listed", "listed above", "shown above", "see above") when the assistant sent no visible text since the user last spoke: a table written only in thinking was never shown. The turn is read with `scripts/extract-session-text.py --since-last-user` (a typed prompt or an earlier question's answer ends the previous turn); fails open when the transcript cannot be read. A second trigger refuses a question naming a file path (html, png, pdf, md, json, zip and the like; URLs excepted) unless that path's absolute form was sent in visible text since the user last spoke, and a relative path in the question is always refused. A third, needing no transcript, refuses a letter label ("pair A", "B or C", "option B") that the question and its options never define ("B: …", "B (…)"). Before refusing for missing visible text it re-reads the transcript up to three times a second apart, because a text block sent in the same message as the question can reach the file after the hook runs. Covers `docs/on-demand/asking-for-decisions.md`; cases in `hooks/tests/run-require-question-facts-in-question.sh` |
| `hooks/require-user-quote-before-session-message.py` | PreToolUse (`SendMessage`) | Refuses a message to another session unless the call's `summary` quotes (in double quotes) words the user typed, or answered in an AskUserQuestion, after this session's previous message to a peer; one instruction covers one message. A send to `main` or to a sub-agent this session spawned is exempt; a sub-agent's send to anyone else is refused. Reads the transcript through `scripts/transcript_items.py`; fails closed. Cases in `hooks/tests/test_require_user_quote_before_session_message.py`, run with `hooks/tests/run-require-user-quote-before-session-message.sh` |
| `hooks/require-approval-before-public-push.py` | PreToolUse (`Bash`) | Refuses a `git push` that sends new commits to a public GitHub repo unless the command carries `# public-push: no personal content` (refused when the outgoing commits add or change an image, video, audio or PDF file) or `# public-push: user approved "<quote>"`, the quote taken from the user's typed words, AskUserQuestion answers or decision-form answers (`<question id>: <option id>` for a pick) since this session's previous approved public push. Rewinds, deletes, private and non-GitHub remotes pass. Visibility from `gh repo view`, cached a day under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/repo-visibility/`; fails closed when unknown. Cases in `hooks/tests/test_require_approval_before_public_push.py`, run with `hooks/tests/run-require-approval-before-public-push.sh` |
| `hooks/require-subagent-sizing.sh` | PreToolUse (`Agent`) | Refuses a sub-agent spawn that sets no `model`; a session's first spawn that names a model passes with the table and size limits attached as `additionalContext` (the once-per-session marker lives under `${XDG_CACHE_HOME:-$HOME/.cache}/agents-shared/subagent-sizing/`, so a resumed session keeps it); fills in the table's `effort` (haiku low, sonnet medium) when one is missing, via `updatedInput`; `fork` is exempt. The table comes from `docs/size-subagents-to-the-task.md`, which is not loaded as a rule; cases in `hooks/tests/require-subagent-sizing-cases.tsv`, run with `hooks/tests/run-require-subagent-sizing.sh` |
| `hooks/require-fetch-before-commit.sh` | PreToolUse (`Bash`) | Before a `git commit` or `git -C DIR commit`, fetches the branch's remote (4 s limit, `FETCH_BEFORE_COMMIT_LIMIT`) and refuses the commit once, per session, repo and upstream tip, when the branch is behind its upstream: names up to five remote commits and says `git pull --ff-only`, or `git pull --rebase` when the branch has unpushed commits. Passes silently with no upstream, a detached HEAD, no repository, or a fetch that fails or times out. Marker under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/fetch-before-commit/`. Covers `claude/rules/commit-atomically-as-you-build.md`; cases in `hooks/tests/require-fetch-before-commit-cases.tsv`, run with `hooks/tests/run-require-fetch-before-commit.sh` |
| `hooks/require-clean-env-for-app-launch.sh` | PreToolUse (`Bash`, `Write`, `Edit`) | Refuses `open` with `-a`, `-b` or a `.app` argument, typed in a command or in a script an agent writes, edits or runs (`zsh FILE`, `./FILE`, `source FILE`): `open` hands the app the agent's whole environment, and an app keeps it for everything it starts (a terminal gives every new tab the agent's `CLAUDE_*` session variables, so new sessions there save no transcript, and its `TMUX` pane). Points at `scripts/open-app-for-user` (`open -g` under `env -i`, as the Dock launches) for an app the user will use, and `quiet-open` for an agent-only window. Covers `claude/rules/rebuild-and-restart-local-tools-after-changes.md` and `window-focus.md`; cases in `hooks/tests/require-clean-env-for-app-launch-cases.tsv`, run with `hooks/tests/run-require-clean-env-for-app-launch.sh` |
| `hooks/show-rule-at-action.sh` | PreToolUse (`Bash\|Write\|Edit\|SendMessage\|AskUserQuestion\|WebFetch\|WebSearch\|mcp__exa__.*`) | Shows a rule's full text (`docs/on-demand/<id>.md`) the first time a session makes the tool call that rule covers, so the text need not load into every session. `hooks/rule-triggers.tsv` holds one row per trigger (tool, pattern, mode `deny-once` or `note-once`); moving another rule out of `claude/rules/` is a new row and a new doc, with no settings edit; cases in `hooks/tests/show-rule-at-action-cases.tsv`, run with `hooks/tests/run-show-rule-at-action.sh` |
| `hooks/focus-policy.sh` | SessionStart | Tells the session whether this machine tolerates a window stealing keyboard focus |
| `hooks/note-skill-groups-used-here.sh` | SessionStart | On a fresh start in a repo where a globally-off skill group was used in the last 30 days, names it until the repo records a choice in `enabledPlugins`; reads the cache `scripts/report-skill-group-use.py --write-cache` keeps, refreshed daily by `jobs/rule-failure-survey`; cases in `hooks/tests/run-note-skill-groups-used-here.sh` |
| `hooks/record-clo-session.zsh` | SessionStart, SessionEnd | Never blocks, prints nothing. Inside tmux, writes the Claude session id and folder under the tmux session's name (`${XDG_STATE_HOME:-~/.local/state}/agents-shared/clo-sessions/<name>`); `scripts/clo` reads it when the tmux session ends and leaves "closed notebook-7f · <id> · <folder>" in the tab, since in iTerm's tmux mode the pane and whatever Claude printed on exit go away with the session. SessionEnd rewrites it, so a `/clear` leaves the new id. Cases in `hooks/tests/run-record-clo-session.sh` |
| `hooks/memory-lint.sh` | PreToolUse (`Edit\|Write`) | Keeps auto-memory index lines topic-only and refuses a memory that duplicates a rule |
| `hooks/dump-hook-stdin.sh` | any | Probe: writes the JSON a hook event receives to a file, then allows the call |
| `hooks/subagent-guard.sh` | PreToolUse (`Task\|Agent`) | Refuses a spawn from inside a subagent; past 8 spawns in a session asks once, then allows the rest of that session. The 8 is overridden per Claude account, per machine, by `${XDG_CONFIG_HOME:-~/.config}/agents-shared/subagent-spawn-budget` (a number or `unlimited`; shape `scripts/subagent-spawn-budget.example`, read by `scripts/subagent-spawn-budget`; a bad line makes every spawn ask with the error). CC Sessions' row menu approves one session in advance (`/tmp/claude-spawn-asked-<session id>`), its Guards menu every session (`<config>/subagent-guard/bypass-all-sessions`, until removed), and a session launched with `CLAUDE_SUBAGENT_GUARD_BYPASS=1` (set by an orchestrator on the unit sessions it starts) skips the ask; nesting stays refused in every case. Wired as `<config>/hooks/subagent-guard.sh`, a symlink to this file. Cases in `hooks/tests/run-subagent-guard.sh` |
| `hooks/ssh-request-guard.sh` | PreToolUse (`Bash`) | Asks before an ssh command that could send requests from a remote host: network programs, code in a container, tunnels, scripts fed over stdin; read-only inspection in a container passes. A host the user clears for one session with `allow-ssh-host-for-session HOST SESSION_ID` (user-run, never agent-run) skips those asks in that session only; the file `<config>/ssh-request-guard/bypass-all-sessions` (CC Sessions' Guards menu) skips them in every session until removed. Every ask is appended to `<config>/ssh-request-guard/asks.jsonl`; `scripts/review-ssh-guard-asks.py` joins the log with the transcripts to show which asks were approved or denied |
| `hooks/nudge-transcript-parsers.sh` | PreToolUse (`Bash\|Write`) | Never blocks. Once per session, when a command or a written file reads `~/.claude/projects` with python, jq, node or similar and names no shared reader, adds one `additionalContext` note pointing at `scripts/extract-session-text.py` and the mine-chat-logs skill. State file per session in `<config>/nudge-transcript-parsers/`; cases in `hooks/tests/nudge-transcript-parsers-cases.tsv`, run with `hooks/tests/run-nudge-transcript-parsers.sh`. Covers `claude/rules/never-hand-roll-a-transcript-parser.md` |
| `hooks/note-published-source-edited.sh` (forwards to `hooks/personal/`; personal profile only) | PostToolUse (`Edit\|Write\|MultiEdit`) | Never blocks. Once per session per file, when the file an agent just changed is the recorded source of a note published with `notes-publish` (checked with `notes-publish --where`), adds one `additionalContext` note: the published copy is now out of date; report it, do not republish unasked. Misses edits made through Bash. State per session in `<config>/note-published-source-edited/`; cases in `hooks/tests/run-note-published-source-edited.sh`. Covers the notes-shared repo's published-note records |
| `hooks/note-secret-in-tool-output.py` | PostToolUse (`Bash\|Read\|Grep`) | Never blocks, no model. When a tool's output holds text shaped like a credential (a password, secret, token or API-key field with a literal value; a known token prefix such as `sk-`, `ghp_`, `xox?-`, `AKIA`, `AIza`, `sk_live_`; a JSON web token, a bearer token, or a private key block), adds one `additionalContext` note: the secret is exposed, tell the user once in the next reply where it came from, repeat nothing of it anywhere, do not open the source again or use it. Never prints, logs or stores the match; for Bash the note says "this command" rather than quoting it. Values that are code, a variable's name, a template, a placeholder or a pointer to a store (`keychain:`, `op://`) do not count. Once per source per session, marked by a hash under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/note-secret-in-tool-output/`; fails open. Added 2026-11-21, after a command printed a password from a personal note and the agent kept it from the owner. A bare password with no label passes it; the "Private content" section of `claude/rules/working-style.md` covers that. Cases (made-up credentials built at run time) in `hooks/tests/run-note-secret-in-tool-output.sh` |
| `hooks/nudge-named-skills-and-stale-shells.sh` | UserPromptSubmit | Never blocks, no model. Adds one line to the context when a typed prompt names a skill or command from the roster (invoke it with the Skill tool), and one when this session has background shells running over 60 minutes. The prompt never waits on the shell check: it prints the cached result and refreshes a cache older than 5 minutes in a detached process, so a session's first prompt carries no shells line |
| `hooks/refuse-idle-end-of-turn.sh` | Stop | Refuses, once per turn (`{"decision":"block"}`), an end of turn that leaves the session idle: the last text offers work or poses a choice in prose ("want me to", "say the word", "if you'd like", "the choice is"), or nothing was asked with AskUserQuestion since the user's last prompt (or work followed the answer), no background work launched since then is unreported (Agent spawn, background Bash, Monitor, ScheduleWakeup, CronCreate against task notifications and hand-backs), and the last line is not `Nothing left: …`. When the prompt also says to continue (`hooks/continue-request-pattern.txt`: "list me X and continue", "show me and proceed"), a text-only end after delivered content passes only when the turn armed a ScheduleWakeup, Monitor, background Agent or background Bash call, or an earlier launch is still unreported; otherwise it is refused once with a message to arm a wakeup (2026-11-13). Offer phrases inside a fenced block (``` or ~~~, a message handed on for copying) are not read as an offer. Passes when `stop_hook_active` is true, during an open away stretch, when the user's last prompt says stop, and on any read failure; reads the transcript with `scripts/extract-session-text.py`. Replaced the log-only `log-buried-go-ahead.sh` on 2026-10-28, after 122 typed nudges in a month. Covers `claude/rules/end-every-turn-with-a-next-step.md`; cases (built and real transcript tails) in `hooks/tests/run-refuse-idle-end-of-turn.sh` |
| `hooks/end-turn-for-queued-slash-command.py` | PostToolUse (all tools), PreToolUse (`AskUserQuestion\|Skill`) | Claude Code folds a plain-text message queued mid-turn into the turn but holds a queued slash command until the turn ends, which the agent cannot see. While one is queued (`scripts/transcript_items.py` `pending_queued_commands`, replaying the transcript's `queue-operation` records), it adds a note after a tool call, once per command: finish the step, end the turn in text. It also refuses AskUserQuestion, which keeps the turn open, and a Skill call for the queued command, which would run it twice. 2026-11-12: a queued `/pattern-discovery-agent-fix` waited 18 minutes behind work and two questions ("IT STILL IS QUEUED ... WHY"); 10 of 1,286 transcripts ended with a slash command never delivered. Marker per session under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/end-turn-for-queued-slash-command/`; fails open; cases in `hooks/tests/run-end-turn-for-queued-slash-command.sh` |
| `hooks/refuse-requested-content-before-tool-call.sh` | PreToolUse (`AskUserQuestion\|Skill\|Agent\|SendMessage\|Bash\|Edit\|Write`) | Refuses (exit 2) four things; the first three once per turn. (1) For a question, skill, agent or session-message call: a call made right after the agent wrote content the user asked to see (the user's last prompt matches `hooks/show-request-pattern.txt`: "list me", "show me", "give me", "where is", "table", "all the"; the turn holds 40+ characters of text or a list or table, with no answered call of these tools since). (2) For any of the seven tools, whatever the prompt: a call made right after the agent wrote a copy-ready draft (a fenced code block) in the same turn, with no answered call since; for Bash, Edit and Write it exits at once when the transcript holds no fence. (3) For Edit, Write and a Bash call that is not obviously read-only (an unknown command, `git commit`, a redirect to a file, `sed -i`): a call made when the user's last prompt matches the show pattern and the turn holds no delivered content yet (under 200 characters of text and under two list or table lines, so a one-line announcement does not count). Read-only Bash (ls, cat, grep, `git status`/`log`/`diff`, `gh ... view`/`list`, jq, sed without `-i`) gathers the data for the answer and is never refused. Its reason says to deliver the content as text first and then continue with the work (incident 2026-11-13, "list me /outstanding and continue" followed by many edits before any list). Text before a tool call can show as one summary line on the user's screen. The reason says to end the turn with the content (or the draft) as the last text and no tool call, and call next turn. `refuse-idle-end-of-turn.sh` reads the same pattern and lets such a text-only turn end without a proceed question. (4) For Edit, Write and a Bash call that is not obviously read-only: a call made when the user's latest message was queued mid-turn and nothing has replied to it (no assistant text, no question form the user answered); a typed prompt does not trigger it, and hand-backs, notifications and Stop-hook feedback do not count; the transcript is re-read up to three times, a second apart, before refusing, since a reply written in the same message as the call may not be in it yet; the refusal quotes the message and says to reply, then repeat the call; no marker, it ends when the reply exists (incident 2026-11-15, "what do you mean?" and "I am not alex claude", queued mid-turn, followed by edits and pushes with no reply). A question form the user answered after the prompt also lifts (3). Read-only Bash also covers `git submodule status` and this repo's transcript readers without `--out`. Never refuses a sub-agent call (the input carries `agent_id`). Marker per session and prompt under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/refuse-requested-content-before-tool-call/`; fails open; cases in `hooks/tests/run-refuse-requested-content-before-tool-call.sh` |
| `hooks/open-away-stretch.sh` | UserPromptSubmit | A prompt that starts with `/away` opens an away stretch for the session: `/away until HH:MM` (local, next occurrence), `/away for 2h`, `/away off` closes it, a bare `/away` is refused with the usage. A stretch always ends, at most 12 hours out; no other prompt, task notification or wakeup closes it. State is one file per session in `${XDG_STATE_HOME:-~/.local/state}/agents-shared/away/`, kept by `scripts/away-obligation` (`open`, `close --reason`, `status`). No network, no model call. Cases in `hooks/tests/away-prompt-cases.tsv`, run with `hooks/tests/run-away-stretch.sh` |
| `hooks/refuse-stop-while-away.sh` | Stop | During an open away stretch, refuses to let the session end its turn while nothing is armed to wake it (`{"decision":"block"}`): armed is a live background shell of the session (`scripts/list-session-background-shells.sh`, a Monitor does not count) or a standing `ScheduleWakeup`/`CronCreate` call since the user last spoke (read with `scripts/extract-session-text.py`). Lets the stop through when `stop_hook_active` is true, after 2 refusals in the stretch (logged to `away/log.jsonl`, then `notify`), when the stretch is closed or past its end, and on any read failure. Added after 2026-10-19, when a session filed a job for 09:00, ended its turn and sat idle seven hours. Covers the "While the user is away" section of `claude/rules/working-style.md`; cases in `hooks/tests/away-stop-cases.tsv`, same runner |
| `hooks/refuse-unasked-draft-reply.sh` | Stop | Refuses, once (`{"decision":"block"}`), a final reply whose last text holds a fenced block shaped like a message (first line a greeting or an @-mention followed by words, no code punctuation, English or Turkish; no sign-off required since 2026-11-12) when the user's last typed prompt carried a pasted image or `<pasted_content>` and no AskUserQuestion was called since. The reason asks the agent to check the pasted message for a question the user has not answered and to drop stock lines. Passes when `stop_hook_active` is true and on any read failure; reads the transcript with `scripts/extract-session-text.py`. Added 2026-10-25, when a draft answered a meeting-time question for the user. Covers `claude/rules/drafting-messages-for-the-user.md`; cases in `hooks/tests/run-refuse-unasked-draft-reply.sh` |
| `hooks/note-lesson-on-revised-draft.sh` | Stop | Blocks once (`{"decision":"block"}`) when the last reply holds a message-shaped fenced block (first line a greeting or an @-mention followed by words, no code punctuation) and the reply before the user's last typed prompt held one too: a revised draft. The reason asks the agent, if the user's answer corrected the draft, to add or sharpen a row in the Lessons table of a listed drafting skill, verbatim and dated. Passes when `stop_hook_active` is true and on any read failure; reads the transcript with `scripts/extract-session-text.py`. Added 2026-11-12. Covers `claude/rules/drafting-messages-for-the-user.md`; cases in `hooks/tests/run-note-lesson-on-revised-draft.sh` |

### memory-lint.sh

`MEMORY.md` loads into every session in its project; the memory files load only
on recall. A fact in an index line is therefore paid for in every session and
is where private detail leaks. On any `Edit` or `Write` under
`<config>/projects/*/memory/` this checks the two halves a script can check:

- a new or changed index line must be a topic label — no digits, no currency
  symbol, at most 12 words after the dash. Entries whose file says
  `type: feedback` are exempt, because a prohibition has to fire before the
  mistake and so keeps its instruction in the line
- a memory file being created must not share its slug with a rule in
  `<config>/rules/`

Only lines being introduced are judged, so rewriting an index that already
carries old offenders is not blocked for them. The rule that says what to
write is `docs/on-demand/memory-hygiene.md`; this refuses what it can detect.

**Fails closed**, like the other PreToolUse guards. Cases in
`hooks/tests/memory-lint-cases.tsv`, run with `hooks/tests/run-memory-lint.sh`.

```json
{ "matcher": "Edit|Write", "hooks": [{ "type": "command", "command": "…/hooks/memory-lint.sh", "timeout": 10 }] }
```

### dump-hook-stdin.sh

Point any hook event at it and it writes the JSON it received to
`$HOOK_STDIN_OUT` (else `<config>/hook-stdin.json`), then exits 0. That answers
"what does this event actually get?" — which fields `tool_input` carries, what
`cwd` and `permission_mode` look like — before writing a hook that depends on it.

### focus-policy.sh

Agents open windows: a Godot capture, a browser, a simulator. On a machine the
user is working on, that grabs focus mid-sentence, and an iteration loop does it
repeatedly. Whether it is acceptable depends on the **machine**, not the task, so
the answer belongs in the environment rather than in each session's judgement.

```bash
hooks/focus-policy.sh            # SessionStart — injects the verdict + guidance
hooks/focus-policy.sh --verdict  # "allow" | "deny"
hooks/focus-policy.sh --check    # exit 0 = allowed, 1 = denied
```

The session-start line reads `Focus policy: ALLOW · quiet-open: /path` (or
`quiet-open: not installed`). The verdict is a tolerance for the interruption,
not a licence: a window that activates hides a hotkey terminal on either kind of
machine, so windowed apps go through `quiet-open` (the `tools` repo) under either
verdict, and only an app it cannot quiet becomes an ask. `--verdict` and
`--check` are consumed by scripts and never change shape.

**Fails closed.** An unknown machine is `deny`: forgetting to allow one costs a
little convenience, forgetting to deny one costs the user their attention.

The allow-list is `focus-allow` in the Claude config dir (`$CLAUDE_CONFIG_DIR`,
else `~/.claude`) — one hostname or glob per line, `#` comments ignored. There is
no list in the script: machine names are local configuration, not shared source,
so a missing or empty file denies everywhere.

Wire it up in that same directory's `settings.json`:

```json
{ "type": "command", "command": "<abs-path>/hooks/focus-policy.sh", "timeout": 5 }
```

The matching standing rule is `claude/rules/window-focus.md` — the hook
reports the verdict and whether `quiet-open` is present, the rule says what to
do about both.

### system-one

The local decision model server and the `system-one ask` call agents use for a bounded judgment live in
the private `system-one` repo (`SYSTEM_ONE_DIR` in `paths.local.sh` is its checkout); its README is the
documentation. It has no hooks beyond the session-start one. The skill-name nudge and the stale-shells
warning that used to ride on its prompt hook are `hooks/nudge-named-skills-and-stale-shells.sh` here.

### githooks/pre-push: the name guard for public repos

A git hook, not a Claude Code hook, so it covers every push from the clone, an agent's or one
typed in a terminal. `githooks/pre-push` first asks whether the repo is private: for a github.com
remote it runs `gh api repos/OWNER/NAME --jq .private` and caches the answer per repo for 7 days
under `${XDG_CACHE_HOME:-~/.cache}/agents-shared/repo-visibility/` (delete a repo's file there to
force a fresh look; a repo made public stays "private" in the cache until then or until 7 days pass).
A private repo passes unscanned. A public one is scanned by `githooks/scan-push-names`. When the
visibility is unknown (gh missing, offline, an API error, a remote that is not github.com) it
scans and prints one line saying so: unknown never passes silently.

The scan reads every commit being pushed (message, author and committer, touched
paths, added lines, binary files), annotated tag messages, and the full tree at each pushed tip,
and refuses the push when a line matches an entry of the untracked denylist at
`${XDG_CONFIG_HOME:-~/.config}/agents-shared/push-denylist.txt` (`$AGENTS_PUSH_DENYLIST`
overrides): one entry per line, a whole word matched case-insensitively, or `re:<ERE>`. The
shape is `githooks/push-denylist.txt.example`. A missing list refuses every push that is scanned
(a private repo's push never reaches that check); a list with no entries
lets the push through but prints a loud warning (the hook on each push, `init-global.sh` on each
run), since it checks nothing. When git cannot list the commits, the push is refused.

**A public repo whose job is to name those entries** (a CV listing its owner's employers) is exempt
when its `OWNER/NAME` is a line of the untracked
`${XDG_CONFIG_HOME:-~/.config}/agents-shared/push-denylist-exempt.txt` (`$AGENTS_PUSH_DENYLIST_EXEMPT`
overrides; text after `#` is skipped). The line matches the remote URL's last two path parts without
regard to case, so every clone of that repo is covered, a deploy tool's own clone included. An exempt
push is not scanned, and the hook prints one line saying so on every push.

**The repo's own hooks still run.** A `core.hooksPath` makes git ignore `.git/hooks/`, where git-lfs
installs `pre-push`, `post-checkout`, `post-commit` and `post-merge`. After a passing scan,
`githooks/pre-push` runs the repo's own `<git-common-dir>/hooks/pre-push` (if executable) with the same
arguments and stdin, and fails when it does. Every other client-side hook name in `githooks/` is a
symlink to `chain-hook`, which runs the repo's own hook of that name the same way. A repo with no hook
of its own is unaffected.

That makes it safe to set globally, which is the recommended setup on a **personal** machine, so every
public repo is covered without opting each in:

```bash
git config --global core.hooksPath "$AGENTS_SHARED/githooks"
```

`init-global.sh` prints this line when it is not set and never sets it itself. A repo's own
`core.hooksPath` still wins over the global one, so that repo's pushes are never scanned: when the
global one is set, `init-global.sh` lists every public repo under `$DEV_ROOT` that has a hooks path of
its own (`scripts/list-push-guard-bypasses.zsh`, which asks `gh` for visibility and shares the hook's
cache), unless it is in the exempt list. On a **work** machine do not set it globally: it
would run on the employer's repos. Opt in per repo (below), and write that machine's denylist by
hand with only the employer's own names and internal terms, never a copy of the personal machine's list.

`init-global.sh` sets `core.hooksPath` to `githooks` for this repo (leaving any
other value alone, and saying so). Another repo opts in with

```bash
git -C <repo> config core.hooksPath "$AGENTS_SHARED/githooks"
```

`scripts/tests/test-pre-push-denylist.zsh` tests it against throwaway repos, with `gh` stubbed on PATH.

## Updating

`git pull` in the clone. Edits to existing files take effect immediately — the
symlinks already point here. After a file is **added, renamed, or deleted**,
re-run `bash scripts/init-global.sh` to sync the links.

## Skill Groups

External packs live in **groups**: a directory under `claude/skills/` holding a
`.claude-plugin/plugin.json` and a `skills/` folder of skills. Claude Code loads
such a directory as a plugin named `<group>@skills-dir` — discovered in place
through the symlink, no marketplace, no install, no cache copy — and its skills
are invoked as `/<group>:<skill>`. Grouping is what makes a pack switchable:

```bash
claude plugin disable gamedev@skills-dir --scope user     # off everywhere
claude plugin enable  gamedev@skills-dir --scope project  # on for this repo, committed
claude plugin list                                        # what is on here
claude plugin details gamedev@skills-dir                  # what it costs in context
```

A disabled group costs nothing; an enabled one loads its skill descriptions like
any other skill.

**Defaults are committed.** Claude Code loads a group nobody names, so `claude/skill-groups.json`
names every group under `defaults` (off, unless a group should load everywhere), and
`scripts/init-global.sh` writes any missing one into the config folder's `settings.json` through
`scripts/sync-skill-group-settings.py`; a group switched on or off by hand keeps that choice.
`check-skills.zsh` fails when a group has no default or a default names no group, so a new group
is added there in the same commit. `splits` records each group split (old group: new groups). Skills the machine's owner wrote stay flat under
`claude/skills/<name>/` and keep their bare `/<name>`.

**Sizing a group.** A group is one toolchain or task and holds about 20 skills or fewer: a
repo that enables it loads every description in it, so a pack mixing several toolchains
(`motion` was graphics, web animation and GSAP) is split. A router skill is enabled together
with the groups it routes to. A flat skill that is rarely used is set to name-only in Skill
Tree rather than moved into a group, because a move renames it and rules and repos name it
bare. When a group is split, the repos that enable it and use the moved skills enable the
new groups too: record the split under `splits` in `claude/skill-groups.json` (and the new groups
under `defaults`), and `init-global.sh` runs `sync-skill-group-settings.py --migrate-splits`, which
switches a new group on in each repo whose gitignored `settings.local.json` has the old group on and
whose sessions ran the moved skills (the usage report counts a run under the old name for the
group holding the skill now). A new group a repo never used gets no entry; its default keeps it off.

**Agents switch groups through one script.** `scripts/enable-skill-group.zsh <group> --reason "…"`
(or `--off`) runs `claude plugin enable|disable <group>@skills-dir --scope local` in the repo root,
refuses where the repo commits `.claude/settings.local.json`, and appends the switch and its reason
to `~/.local/state/agents-shared/skill-group-switches.tsv`. The SessionStart hook
`note-skill-groups-used-here.sh` names a group an agent switched on over 30 days ago that has gone
unused, so it gets switched off again.

Skill Tree draws all of this as one page, and lives in the `dev-repos-skills` repo (its `skills`
skin): every group with its skills, the description cost, and the switches: a group per scope for
the project you pick, a skill inside a group as auto or slash-only (a fenced frontmatter edit in
this repo, override.patch regenerated), a flat skill through the four `skillOverrides` states.
It finds this checkout from `$AGENTS_SHARED`, else `agents_shared` in its `config.toml`, and calls
`scripts/usage-survey.py`, `check-skills.zsh` and `vendor-upstream-skill.py` here.

Grouped skills follow the external-skill convention below, one `source.json` per
skill under `<group>/skills/<name>/`; the sync script finds both layouts, and a
group name as its argument syncs the whole group. A skill switched off sits in
`<group>/off/<name>/` instead, which no session scans; nothing inside it changes,
so its slash-only setting and provenance survive the move, and the sync script
still updates it there.

For a skill needed in one session only, skip installation entirely: fetch its
SKILL.md into scratch, read it, follow it.

## External Skills

Some skills are sourced from third-party repos. Each keeps a `source.json` (upstream repo, path, file list, pinned commit) alongside a `.upstream/` pristine base and, if we've adapted it, an `override.patch`.

Updates preserve local edits the way oh-my-zsh's `upgrade_oh_my_zsh_custom` does: rather than overwriting `SKILL.md`, the sync 3-way merges upstream's change into the working files against the stored base, replaying our edits on top. Conflicts are surfaced as markers, never silently dropped.

```bash
bash scripts/sync-external-skills.sh            # all external skills → upstream HEAD
bash scripts/sync-external-skills.sh caveman     # specific skill only
bash scripts/sync-external-skills.sh --dry-run [name]  # preview: behind upstream? merge clean? writes nothing
bash scripts/sync-external-skills.sh --adopt-listing name  # make source.json's file list match upstream's skill dir, then sync
bash scripts/sync-external-skills.sh --check-links [name]  # no network: relative links whose target is not vendored
bash scripts/sync-external-skills.sh --establish-base [name]  # (re)build base + patch from the pin
```

The `/update-external-skills` skill runs the whole procedure (preview, sync, resolve conflicts, commit). See CLAUDE.md → *External (Third-Party) Skills* for the full model.
