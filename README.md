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
config dir (`$CLAUDE_CONFIG_DIR`, else `~/.claude`).

| Hook | Event | Description |
|------|-------|-------------|
| `hooks/block-tree-discard.sh` | PreToolUse | Refuses git commands that discard uncommitted work; only `git checkout -- <one tracked file>` passes |
| `hooks/focus-policy.sh` | SessionStart | Tells the session whether this machine tolerates a window stealing keyboard focus |
| `hooks/memory-lint.sh` | PreToolUse (`Edit\|Write`) | Keeps auto-memory index lines topic-only and refuses a memory that duplicates a rule |
| `hooks/dump-hook-stdin.sh` | any | Probe: writes the JSON a hook event receives to a file, then allows the call |
| `hooks/system-one-start.sh` | SessionStart | Brings up the system-one decision-model server in the background; reports one line, never blocks |
| `hooks/system-one-bash.sh` | PreToolUse (`Bash`) | Scores each command for destructiveness with the decision model; shadow mode logs, act mode asks (never denies) |
| `hooks/system-one-prompt.sh` | UserPromptSubmit | Classifies a typed prompt's kind (question, order, wish, correction, other); shadow mode logs, act mode adds `additionalContext` worded per kind, plus a deterministic (no model call) line when the prompt names a roster skill/command |
| `hooks/system-one-stop.sh` | Stop | Scores the assistant's final message for padding and answer-shape; shadow mode logs, act mode returns `decision: block` with a rewrite instruction |
| `hooks/system-one-ask.sh` | PreToolUse (`AskUserQuestion`) | Scores a question the agent is about to ask (already answered in context, routine default, naming or irreversible, options complete); shadow mode logs, act mode returns `permissionDecision: deny` naming the fired question, but never for a naming or irreversible ask |
| `hooks/system-one-bash-post.sh` | PostToolUse + PostToolUseFailure (`Bash`) | Writes the outcome receipt (`ran`, `exit_code`, `failed`) for the matching Bash verdict row, joined by `tool_use_id` (`state_sha256` for older rows); both events, because a non-zero exit ends in PostToolUseFailure and never reaches PostToolUse; no model call, every mode, never blocks |

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
write is `claude/rules/memory-hygiene.md`; this refuses what it can detect.

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

A local decision model (Laya, one warm server on loopback) that answers typed
questions (`choice`, `score`, yes/no `noul`) about a text state with calibrated
probabilities, for the bounded checks the exact guards cannot enumerate. Design,
measurements and the evaluation plan: `notebook/2026-09-24-system-one-decision-model-integration.md`.

`scripts/system-one` is the wrapper (`start`, `stop`, `status`, `ask`,
`shadow-report`, `install`; `roster` is a stub, unrelated to the two hooks
below). It reaches `~/bin` through the tools repo's `links.txt`. Copy
`scripts/system-one.local.sh.example` to `${CLAUDE_CONFIG_DIR:-~/.claude}/system-one.local.sh`
and set `SYSTEM_ONE_VENV`; the port (7811), idle exit (30 min) and mode have
defaults there, and the Bash hook's thresholds live in the questions file with
`SYSTEM_ONE_BASH_ASK_<QUESTION>` as the override. Each hook's mode can be set
separately (`SYSTEM_ONE_BASH_MODE`, `SYSTEM_ONE_PROMPT_MODE`,
`SYSTEM_ONE_STOP_MODE`, `SYSTEM_ONE_ASK_MODE`), falling back to the shared
`SYSTEM_ONE_MODE`; each hook's model separately too
(`SYSTEM_ONE_{BASH,PROMPT,STOP,ASK}_MODEL`, default `english`).

`SYSTEM_ONE_BACKEND` picks which server `start` launches: `laya` (default) or
`kev`; both speak the same `/v1/systemone` wire shape, so `ask` and every hook
work unchanged either way. `SYSTEM_ONE_MODEL_DIR` (laya only, optional) points
at a fine-tuned Laya checkpoint directory, served **alongside** the published
"english" bundle (both preloaded, `Router max_loaded=2`) via
`scripts/system-one-serve.py`, a shim that registers the checkpoint in Laya's
own model registry under `SYSTEM_ONE_MODEL_NAME` (default:
`SYSTEM_ONE_MODEL_DIR`'s basename, e.g. `full-v1`; lowercase, never one of
Laya's own names) and otherwise runs `laya.serve`'s own code (thread cap,
preload, single-worker pool, `/health`), instead of `laya-serve`; the two
published slots this setup never uses (`multilingual`, `typed-decisions`) are
dropped from the served map, so nothing can make the server fetch them. That
name is what a request's `model` field, `ask --model <name>` (default
`english`), the per-hook `SYSTEM_ONE_{BASH,PROMPT,STOP,ASK}_MODEL` (default
`english`), the shadow-log row's `model` field and `status`'s `loaded` list all
carry, unchanged. `ask` checks the response's `routing.model` against what it
asked for and fails (no log row) on a mismatch, so a row can never claim a
model that did not answer it. For
`SYSTEM_ONE_BACKEND=kev`, `SYSTEM_ONE_KEV_DIR` (required, the kev checkout,
run through `uv run --offline`) and `SYSTEM_ONE_KEV_MODEL` (default
`jaredpalmer/kev-0.8b`; a Hub id or a run directory) select the model; kev has
no `/health`, so `status` probes `/v1/models`. `start` validates the config
before launching anything (a checkpoint directory must hold
`rl_agent_config.json` + `model.safetensors`, a kev run must hold `head.pt`,
a Hub id must be `owner/name[@rev]`) and sets `HF_HUB_OFFLINE=1` on every
shape, so a start never downloads a model. Switching backends is `stop` then
`start`: `start` leaves a running server of another shape alone and says so.

- `system-one-start.sh` runs `system-one start` at SessionStart (it returns at
  once; the server takes about 4 s to load and is warm by the first Bash call).
  Nothing else starts it; a start lock keeps two sessions from launching it twice;
  a watchdog stops it by pid after the idle period. `stop` and the watchdog signal
  only the process group of the pid they wrote (the group covers `uv run` and the
  python it spawns for kev), and only while that pid is still one of the three
  server shapes (`laya-serve`, `system-one-serve.py`, `kev.serve`), never a port
  or a name.
- `system-one-bash.sh` builds `cwd: ...\ncommand:\n...` (each heredoc body cut to
  its first two lines plus a marker by `hooks/system-one-bash-state.awk`), asks the
  four yes/no questions in `hooks/system-one-bash-questions.json` (foreign process,
  irreversible, leaves the machine, network install) and pipes them to
  `system-one ask --fail-open --gate` with that file's thresholds. **Shadow** and
  **show** modes append the verdict to the shadow log and emit nothing (identical
  behaviour; `show` only tells `status`, the status line and Agent Bar Hopping the
  user has opted in to seeing verdicts there); **act** mode emits
  `permissionDecision: "ask"` naming the question that fired. Fails open
  everywhere: no config, no server, timeout. Flip to act only on the user's word,
  after the evaluation plan in the design doc.
- `system-one-prompt.sh` (UserPromptSubmit) first checks the prompt against
  `hooks/system-one-prompt-questions.json`'s `skip_prefixes`/`skip_markers` --
  relayed text (a subagent hand-back, a cross-session message, a task
  notification, a system reminder) matching one exits 0 immediately: no
  model call, no shadow-log row, no annotation, and it is never treated as
  "next prompt" for the outcome receipts below. Otherwise it classifies the
  typed prompt's kind (question, order, wish, correction, other) with that
  same file,
  using `prompt:\n<text>` cut to `state.prompt_chars`, plus, when
  `state.previous_chars` is non-zero and the transcript tail is readable cheaply,
  a `previous:` excerpt of the last assistant message (off by default: measured,
  it raised correction recall and cut overall accuracy). **Shadow** logs only.
  **Act** (section 13 of the design doc) adds `hookSpecificOutput.additionalContext`
  with exactly one line when the top kind's probability is at or above
  `SYSTEM_ONE_PROMPT_ACT_MIN` (config/env, default 0.60, falling back to the
  questions file's `act_min`): question, wish and correction each get a line
  from the file's `context` map (worded from question-handling.md,
  stated-desires.md and answer-shape.md); order and other never do. A slash
  command or a prompt under 3 words is never annotated, whatever it classifies
  as. The line never appears in shadow or show mode. Fails open; kept under
  ~300 ms by bounding the transcript read.

  **Act** carries a third line, the delegate nudge (section 14 of the design
  doc): the same call asks `delegate` ("Should this prompt be handed to a
  subagent rather than done inline?", the question full-v3 was trained on
  from mined Agent spawns) alongside `kind` and `wants_action` -- one
  request, three questions -- and when its probability is at or above
  `SYSTEM_ONE_PROMPT_DELEGATE_MIN` (config/env, default the file's
  `delegate.min`, 0.5) and the prompt has at least `delegate.min_words` (8,
  the mining filter) words, emits the file's `context.delegate` line ("this
  prompt looks like bulk or mechanical work (p=0.NN). Hand it to a Sonnet or
  Haiku subagent..."). Never for a slash command, a relayed message, or in
  show/shadow mode. 0.5 rather than the checkpoint's swept 0.159: on
  full-v3's test split (n=120, 30 positives) precision is 1.00 at 0.5, 0.6
  and 0.7 (recall 0.30/0.27/0.27) against 0.37 at the swept value, so the
  line is rare and right when it appears. The verdict row carries
  `delegate_eligible` and `answers.delegate.noul`. Order of the lines when
  several fire: skill, delegate, kind, newline-joined in one
  `additionalContext`.

  **Act** also carries a second, independent line: a deterministic
  skill-routing rule, no model call, so it still fires even when the
  classification above failed (server down, timeout). It checks the same
  slash-command/3-word gate, then explicitly names a roster skill or
  command: `/<name>` anywhere in the prompt, or the bare name when it is
  hyphenated/multi-token (`stg-msg-cmt`, `search-history`, `new-repo`,
  `be-literal`, ...) or listed in `skill_name_rule.allow_bare`
  (single-word names that would otherwise collide with ordinary English --
  `archify`, `humanizer`, `homelab-connect`). The roster is a literal ls of
  `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/*/SKILL.md` and `.../commands/*.md`
  at runtime (top-level only: a plugin group directory such as `interface/`
  or `motion/` has no `SKILL.md` of its own, so its sub-skills are out of
  scope), cached under `STATE_DIR/skill-roster.cache` for
  `skill_name_rule.roster_ttl_seconds` (default 600s). A match immediately
  followed by a `--flag` token is skipped (a pasted `search-history --resume`
  shell line, not a request). One or more matched names produce one line,
  `system-one: this prompt names the skill(s) /<name>[, /<name>...]; invoke
  it/them with the Skill tool instead of doing the work by hand.`, emitted
  first when several lines fire (skill line, delegate line, kind line,
  newline-joined in one `additionalContext`). Measured against
  `~/.local/state/system-one/train/skill_route.jsonl` (448 mined rows,
  2026-09-26): precision 0.80, recall 0.42 on the 15 skills that set tracks
  (fired_lines=56, tp=45, fp=11) -- short of a 0.90 target; the remaining
  false positives are cases a no-model textual rule cannot separate (the
  same phrase, e.g. `/stg-msg-cmt your changes`, labelled both a real
  invocation and a no-op elsewhere in the mined set). See the
  `_skill_name_rule_comment` in the questions file for the full accounting
  and what was tried. Added hook cost: ~5ms roster build (cold, once per TTL
  window; pure bash, no forked `basename`/`dirname`) plus ~15-20ms per call
  for the match itself (roster read, flatten, one `awk` pass) -- measured
  directly around this block, well inside the ~300 ms budget; the test
  runner's own latency failures below are dominated by the model round trip
  (shadow mode, unrelated to this rule) and vary with machine load.

  The prompt hook also writes the **outcome receipts** (section 13): at the
  *next* prompt of the same session it labels the *previous* prompt's verdict
  row with `{"kind":"outcome","ref":<id>,"next_kind","next_is_command","acted","tool_calls"}`
  (`acted`/`tool_calls` come from counting assistant `tool_use` blocks in the
  transcript between the two prompts), and labels every not-yet-labelled
  `stop` row of the session with
  `{"kind":"outcome","ref":<id>,"next_prompt_kind","next_command","ran_outstanding"}`
  -- `next_command`/`ran_outstanding` stay useful data on the row regardless of
  which questions the Stop hook asked. Both happen in every mode,
  including shadow, and read/append the shadow log directly rather than
  through the wrapper (latency). `hooks/system-one-bash-post.sh` (PostToolUse
  and PostToolUseFailure, matcher `Bash`: Claude Code sends a non-zero exit
  to the failure event only, with `error` starting `Exit code N`, while a
  success arrives with a `tool_response` that carries no exit code at all)
  does the same for the Bash hook, joining on the `tool_use_id` the PreToolUse
  hook now logs on its row (the rebuilt `state_sha256` for rows from before
  that), appending `{"kind":"outcome","ref":<id>,"ran":true,"exit_code":<0, N
  or null>,"failed","interrupted"}`; a bash verdict row with no outcome row by
  the next prompt means the command did not run.
  `scripts/system-one-receipts.py` joins verdict and outcome rows across every
  session and reports per-hook agreement (`--hook <name>` to narrow), or
  `--export-cases <hook> <tsv>` writes a labelled cases TSV in the
  `hooks/tests` shape from the outcomes for the next fine-tune (meaningful for
  `prompt` and `stop`; `bash` and `ask` have no outcome-derived gold label yet
  and export zero rows, documented in the file). The prompt and stop hooks log
  their full state (`--keep-state`: the prompt cut to 600 characters, the
  message excerpt cut to 1500, under the state dir only) so an export carries
  the text the model saw; rows from before that carry the 80-character
  `state_excerpt` and are marked `excerpt-only`. `hooks/tests/run-system-one-receipts.sh`
  checks the joins and the export shapes on a fixture. Every verdict row since
  this shipped carries an `id` (`ts`, the state sha's first 8 hex characters
  and the wrapper's pid -- two calls in the same second can otherwise share a
  timestamp and state hash, so the pid is what separates them) and a
  `ts_epoch`; older rows have neither and are simply never referenced.
- `system-one-stop.sh` (Stop) makes one call per Stop, from the state (the
  message's first 1,500 characters plus a
  `length_chars/tables/headers/bullets` line -- `build_stop_state` in
  `scripts/system-one-measure.py`, shared with `scripts/system-one-train-data.py`,
  so a fine-tune trains on exactly what the hook sends), on
  `SYSTEM_ONE_STOP_MODEL` (default `english`): `needless_table` plus `overlong`,
  the padding/answer-shape check. The `pregate.max_chars`-with-no-table skip
  (answer-shape.md's own rule) skips the call entirely, logging nothing.
  **Shadow** logs the verdict, nothing else. **Act** returns `decision: block`
  with a rewrite instruction when `needless_table` (or `overlong`) reaches the
  file's gate, but only when `stop_hook_active` is false, so a revision is
  never blocked again. Fails open; kept under ~500 ms. (A `will_run_outstanding`
  third question and a second, parallel call scoring the `/outstanding`
  predictor ran here 2026-09-25 - 09-26; dropped 2026-09-26 by the user's
  decision. Logged rows from that window are untouched on disk.)
- `system-one-ask.sh` (PreToolUse, matcher `AskUserQuestion`) scores each
  question of the ask, one model call per question launched in parallel, with
  `hooks/system-one-ask-questions.json`'s three `noul` questions:
  `answered_in_context` (the user already said it), `routine_default` (a
  conventional default or a call a senior engineer would make without asking)
  and `naming_or_irreversible` (naming, publishing, a commit-and-push, a
  delete, sending to a third party: always legitimate per
  `asking-for-decisions.md`). State per question: header, text, options and
  `multiSelect` flag, plus, when `state.recent_prompts` is non-zero, a
  `recent:` block from the transcript tail (off by default: measured, it moved
  nothing). Every shadow-log line carries `q_index` and `q_count`. **Shadow**
  logs only. **Act** returns `permissionDecision: deny` only when every
  question of the call fires and none reaches `naming_or_irreversible_min`, so
  a legitimate ask, or a batch holding one, is never denied. Fails open; about
  200 ms for a single question plus roughly 95 ms per further question (the
  server serialises inference).
- Agents needing a bounded judgment: `echo '{"state": "...", "questions": {...}}' | system-one ask`.
  Do not start Python or the server yourself.

Shadow log: one file per hook per session,
`${XDG_STATE_HOME:-~/.local/state}/system-one/shadow/<hook>/<session_id>.jsonl`
(`bash`, `prompt`, `stop`, `ask`; no session id: `shadow/<hook>/_nosession.jsonl`), one
JSON object per call (hook, latency, sha256 and length of the state, every
answer, `would_act`, `acted`, and for the Bash hook the command itself, which
labelling needs). `system-one shadow-report` reports per hook by default,
`--hook <name>` restricts to one, `--session <id>` restricts to one session
(every hook, unless `--hook` narrows it further); `status` counts lines per
hook. A flat `shadow.jsonl` from before the per-session layout is split by
`session_id` the first time `status` or `shadow-report` runs (renamed to
`shadow.jsonl.migrated`); a flat `shadow/<session_id>.jsonl` from before the
per-hook layout (the Bash hook was the only caller) is then moved into
`shadow/bash/`, both migrations atomic and safe under two concurrent callers.
Since section 13, a hook also appends `{"kind":"outcome","ref":<id>,...}` rows
to the same per-hook logs once the real answer is known (see the prompt/stop/
bash-post entries above); `scripts/system-one-receipts.py` joins them back to
the verdict rows they label and reports the agreement. A reader that wants
only verdict rows (cc-statusline.js's `readVerdict`) skips `kind == "outcome"`.
Cases in `hooks/tests/system-one-{bash,prompt,stop,ask}-cases.tsv` (all
hand-labelled; the prompt file carries the previous assistant message as a
fourth column, the stop file stores newlines as a literal `\n` with a `# next:`
comment naming the prompt that followed each message, the evidence for its
label, and the ask file has one row per question with a `call` column grouping
a multi-question call, the question as `question_json`, the user's typed
`answer`, and a `recent` column with the last 5 user prompts and the last
assistant excerpt that the harness cuts to the questions file's `state`),
run with `hooks/tests/run-system-one-{bash,prompt,stop,ask}.sh`, which check
the hook's plumbing (exit code, shadow-mode silence, latency, a log line
exactly when the hook should have called the model); accuracy against the
labelled cases is `scripts/system-one-measure.py --hook {bash,prompt,stop,ask}`,
which loads the model in-process, builds the state exactly as the hook does
from the same questions file, and reports per-class precision/recall (bash:
gate recall and false-ask rate; prompt/stop: a confusion matrix; ask:
per-question precision/recall plus a confusion matrix for `options_complete`);
`--dump-preds FILE` writes every row's answers for threshold sweeps without
another model pass, and `--no-previous`, `--previous-chars`, `--prompt-chars`
(prompt) and `--whole-ask`, `--recent-prompts`, `--recent-chars`, `--no-recent`
(ask) try state variants. `scripts/usage-survey.py --dump-prompts`, `--dump-stops`
and `--dump-asks` (with `--sample N --seed S` for a stratified, whole-call
sample) regenerate the raw, heuristically labelled rows the cases files start
from.

**Show mode**: the Agent Bar Hopping app (`cc-statusline` repo) reads
`display.json`'s `verdictHook` (`bash`, `prompt`, `stop`, or empty for off) to
drive its own Verdicts window (one hook's questions at a time, in the app's
ordered label maps), whatever `SYSTEM_ONE_MODE` is (see
`notebook/2026-09-24-system-one-decision-model-integration.md` sections 9-10
and 12). The mode name `show` exists only so `status`, the status line and the
app can say the user has chosen to see verdicts; nothing in system-one itself
renders anything, and the shadow log is the only interface between the two
repos. (A `/outstanding`-predictor row on the terminal's fourth row, driven by
`will_run_outstanding`, existed 2026-09-25 - 09-26 and was dropped 2026-09-26.)

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
any other skill. Skills the machine's owner wrote stay flat under
`claude/skills/<name>/` and keep their bare `/<name>`.

`scripts/skill-tree.py` draws all of this as one page on loopback — every group
with its skills, the description cost, and the switches: a group per scope for
the project you pick, a skill inside a group as auto or slash-only (a fenced
frontmatter edit in this repo, override.patch regenerated), a flat skill through
the four `skillOverrides` states. It reaches `~/bin` as `skill-tree` through the tools repo's `links.txt`;
`scripts/make-skill-tree-app.zsh` wraps it as *Skill Tree* in `~/Applications`
for Spotlight.

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
bash scripts/sync-external-skills.sh --establish-base [name]  # (re)build base + patch from the pin
```

See CLAUDE.md → *External (Third-Party) Skills* for the full model.
