# TODO

## Stop naming the repo path inside the shared settings.json

### Finding

`~/.claude/settings.json` is synced across machines by the dev-env repo:
`export.sh` copies it verbatim (minus `.feedbackSurveyState`) to
`dev-env/agents/claude/settings.json`, and `import.sh` copies it back. It has no
per-machine variant — that split exists for `.zshrc.<label>`,
`Brewfile.<label>`, `tmux/<label>.conf`, and `asdf/tool-versions.<label>`, but
not for settings.json.

So every path written into settings.json has to be valid on c01
and c02 at the same time. That is why
the hook entries carry a two-candidate probe:

```
for d in "$HOME/dev/personal/agents-shared" "$HOME/dev/agents-shared"; do
    [ -x "$d/hooks/focus-policy.sh" ] && exec "$d/hooks/focus-policy.sh"
done
```

The probe is a workaround for a file that cannot vary per machine, not a
convention worth keeping. It currently appears twice (`focus-policy.sh`,
`block-tree-discard.sh`) and grows by one with every hook added.

The cc-statusline event hook in the same file hardcodes nothing — it is
registered as `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/cc-statusline-event.zsh`,
a symlink that cc-statusline's `scripts/install-event-hook.zsh` creates into the
repo, so the synced entry is valid wherever the repo is checked out.

### What to do

Move the hook scripts into the Claude config dir as symlinks, and reference them
the way the cc-statusline event hook is referenced.

1. Add a third source pair to `scripts/init-global.sh`: `hooks/` →
   `$CLAUDE_DIR/hooks/`, alongside the existing commands and skills pairs. The
   script already resolves the repo root from `${BASH_SOURCE[0]}`, honors
   `CLAUDE_CONFIG_DIR`, repairs wrong-target symlinks, and prunes orphans, so
   the new pair is the same shape as the two already there.
2. Rewrite the two agents-shared entries in `~/.claude/settings.json` to
   `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/<name>.sh`.
3. Run `init-global.sh` on both machines.

Result: the shared settings.json names no repo location. The machine-specific
part is the symlink, created by a script that knows its own path.

### Wrinkles

- `$CLAUDE_CONFIG_DIR` is session-contextual — the `claudep` alias flips it
  (noted in `dev-env/export.sh:14`). `init-global.sh` honors the same variable,
  so the symlinks have to be created once per config dir: `~/.claude` and
  `~/.claude-personal`. dev-env exports both settings.json files separately.
- `~/.claude/hooks/` is not synced by dev-env — only settings.json is. That is
  what makes this work: hook scripts stay machine-local while their
  registration stays shared.
- The `statusLine` entry has the same problem in the same file, but points at
  the `cc-statusline` repo, so this change cannot fix it. cc-statusline now has
  an installer (`scripts/install-event-hook.zsh`) that links its event hook this
  way; extending it to link `cc-statusline.js` too would retire this probe.

### Not doing

Setting `AGENTS_SHARED_DIR` somewhere. In settings.json `env` it would be a
single shared value, so it cannot differ where the repo differs — the problem it
was meant to solve. In `.zshrc.base` with a `.zshrc.c02` override it would
travel correctly, but hook resolution would then depend on the CLI having been
launched from a login shell, which is not true for desktop-app launches.

## Review the log-only go-ahead hook, then decide whether it blocks

`hooks/log-buried-go-ahead.sh` was registered in `~/.claude/settings.json` (Stop) on
2026-10-13 in log-only mode. Nothing reviews it by itself.

The hook triggers the review itself: at 20 logged rows it runs the review script in the background and posts one desktop notification with the true-match rate and verdict, then writes `.review-sent` in its log directory and stays quiet (a "not enough data" verdict retries on a later row). To review early: run `scripts/review-buried-go-ahead-log.py`; it does the join below and prints a verdict (20 rows minimum, 70% true matches to block). By hand: for each row in `~/.local/state/log-buried-go-ahead/*.jsonl`, find the user's next
typed message in that session's transcript (`~/.claude/projects/*/<session_id>.jsonl`). A bare
"proceed", "go", "continue" or "yes" after the row is a true match; any other reply means the
phrase was a false match (a rhetorical question, a quoted phrase).

Decide from the rates: if most rows are true matches, change the hook to return
`{"decision": "block", "reason": "..."}` telling the agent to ask with AskUserQuestion
(`stop_hook_active` guards against a loop). If many are false matches, tighten the pattern
first. Origin: 14 of 144 continue-style nudges (2026-09-14 to 2026-10-13) followed
"say the word and I'll build it"; see
`2026-10-13-claude-code-friction-proposal-v2.html` in the notebook repo.
