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
(`mert-cypher-m3max`) and c02 (`mrtysn-mbp-m2max`) at the same time. That is why
the hook entries carry a two-candidate probe:

```
for d in "$HOME/dev/personal/agents-shared" "$HOME/dev/agents-shared"; do
    [ -x "$d/hooks/focus-policy.sh" ] && exec "$d/hooks/focus-policy.sh"
done
```

The probe is a workaround for a file that cannot vary per machine, not a
convention worth keeping. It currently appears twice (`focus-policy.sh`,
`block-tree-discard.sh`) and grows by one with every hook added.

The peon-ping entries in the same file hardcode nothing — they use
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/peon-ping/peon.sh`, because the
script lives under the Claude config dir rather than in a repo.

### What to do

Move the hook scripts into the Claude config dir as symlinks, and reference them
the way peon-ping is referenced.

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
  the `cc-statusline` repo, so this change cannot fix it. It stays a probe list
  unless cc-statusline grows its own installer.

### Not doing

Setting `AGENTS_SHARED_DIR` somewhere. In settings.json `env` it would be a
single shared value, so it cannot differ where the repo differs — the problem it
was meant to solve. In `.zshrc.base` with a `.zshrc.c02` override it would
travel correctly, but hook resolution would then depend on the CLI having been
launched from a login shell, which is not true for desktop-app launches.
