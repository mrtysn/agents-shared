#!/usr/bin/env bash
#
# init-global.sh — Make agents-shared commands, skills and rules available in EVERY
# project on this machine by symlinking them into the user-level Claude dirs
# (~/.claude/commands, ~/.claude/skills, ~/.claude/rules) instead of each repo's .claude/.
# Hook scripts (hooks/*.sh, *.py, *.zsh, top level only) are linked into ~/.claude/hooks/ the same way, so
# the shared settings.json names them as ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/<name>
# and no repo location.
#
# Idempotent. Re-run after adding, renaming, or removing commands/skills:
#   • new sources are linked
#   • wrong-target symlinks into this repo, and dangling ones, are repaired
#   • live symlinks into another repo (a private skill linked by its own install.sh)
#     are left alone and reported, never repointed
#   • orphaned symlinks (source renamed/deleted upstream) are pruned
#   • real local override files (non-symlinks) are left untouched
#
# Profiles. The target config folder declares AGENT_PROFILE=personal or work in its
# paths.local.sh (read by scripts/agent-profile). claude/rules/personal/ and
# claude/skills/personal/ are linked only when it is personal; on any other profile, or none,
# links into them are removed. Hooks under hooks/personal/ are reached through stubs in hooks/.
# Run once per config folder, with
# CLAUDE_CONFIG_DIR set for any folder other than ~/.claude.
#
# Usage:
#   bash scripts/init-global.sh           # sync ~/.claude with this repo
#   bash scripts/init-global.sh --unlink  # remove every symlink this script created
#
set -euo pipefail
shopt -s nullglob   # an empty glob expands to nothing, not the literal pattern

# Resolve the agents-shared repo root from this script's location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_COMMANDS="$REPO_DIR/claude/commands"
SRC_SKILLS="$REPO_DIR/claude/skills"
SRC_RULES="$REPO_DIR/claude/rules"
SRC_HOOKS="$REPO_DIR/hooks"

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DST_COMMANDS="$CLAUDE_DIR/commands"
DST_SKILLS="$CLAUDE_DIR/skills"
DST_RULES="$CLAUDE_DIR/rules"
DST_HOOKS="$CLAUDE_DIR/hooks"

# Where this checkout lives, published to the shell as $AGENTS_SHARED so skills can
# invoke scripts/ by name instead of carrying a baked-in path. Rewritten on every
# run, so a moved or re-cloned checkout self-heals. $DEV_ROOT names the directory
# holding the other repos skills reach for; it defaults to this repo's parent and
# can be overridden by exporting DEV_ROOT before running.
ENV_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/agents-shared"
ENV_FILE="$ENV_DIR/env.zsh"
DEV_ROOT="${DEV_ROOT:-$(cd "$REPO_DIR/.." && pwd)}"

UNLINK=0
[ "${1:-}" = "--unlink" ] && UNLINK=1

PROFILE="$("$SCRIPT_DIR/agent-profile" "$CLAUDE_DIR")" || exit 1
IN_PROFILE=0
[ "$PROFILE" = personal ] && IN_PROFILE=1

linked=0 fixed=0 pruned=0 out_of_profile=0
skipped_local=()
skipped_foreign=()
RESULT=""

mkdir -p "$DST_COMMANDS" "$DST_SKILLS" "$DST_RULES" "$DST_HOOKS"

# link_one <src> <dst> — point dst at src, reporting the outcome in $RESULT:
#   linked   a new symlink was created
#   fixed    a symlink that pointed elsewhere was repaired
#   current  already correct, nothing to do
#   skipped  a real (non-symlink) file is there — a local override; left as-is
#   foreign  a live symlink into another repo (a private skill of the same name,
#            linked by that repo's install.sh) — left as-is, never repointed
link_one() {
    local src="$1" dst="$2" target
    dst_last="$dst"
    if [ -L "$dst" ]; then
        target="$(readlink "$dst")"
        if [ "$target" = "$src" ]; then RESULT=current; return; fi
        # A dangling link is ours from a moved checkout: repair it. A live one
        # pointing outside this repo belongs to another repo: leave it.
        case "$target" in
            "$REPO_DIR"/*) ;;
            *) if [ -e "$dst" ]; then RESULT=foreign; return; fi ;;
        esac
        rm "$dst"; ln -s "$src" "$dst"; RESULT=fixed; return
    fi
    if [ -e "$dst" ]; then RESULT=skipped; return; fi
    ln -s "$src" "$dst"; RESULT=linked
}


# prune_dir <dst_dir> <src_dir> — drop symlinks that point into src_dir but whose
# target no longer exists (renamed/removed upstream), and links into src_dir/personal/
# when the profile is not personal. With --unlink, drop every symlink into src_dir,
# tearing down what this script created. Foreign symlinks and real files are never
# touched.
prune_dir() {
    local dst_dir="$1" src_dir="$2" link target
    for link in "$dst_dir"/*; do
        [ -L "$link" ] || continue
        target="$(readlink "$link")"
        case "$target" in "$src_dir"/*) ;; *) continue ;; esac
        if [ "$UNLINK" = 1 ] || [ ! -e "$link" ]; then
            rm "$link"; pruned=$((pruned + 1))
        elif [ "$IN_PROFILE" = 0 ]; then
            case "$target" in
                "$src_dir"/personal/*) rm "$link"; out_of_profile=$((out_of_profile + 1)) ;;
            esac
        fi
    done
}

# ── Teardown: remove our symlinks and stop ──────────────────────────────────
if [ "$UNLINK" = 1 ]; then
    prune_dir "$DST_COMMANDS" "$SRC_COMMANDS"
    prune_dir "$DST_SKILLS"   "$SRC_SKILLS"
    prune_dir "$DST_RULES"    "$SRC_RULES"
    prune_dir "$DST_HOOKS"    "$SRC_HOOKS"
    [ -f "$ENV_FILE" ] && rm "$ENV_FILE"
    [ "$(git -C "$REPO_DIR" config --local --get core.hooksPath 2>/dev/null)" = githooks ] &&
        git -C "$REPO_DIR" config --local --unset core.hooksPath
    own_pre_commit="$(git -C "$REPO_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)/hooks/pre-commit"
    [ "$(readlink "$own_pre_commit" 2>/dev/null)" = "$REPO_DIR/scripts/pre-commit-check.zsh" ] && rm "$own_pre_commit"
    printf '\n=== agents-shared global teardown ===\n'
    printf '  Target:           %s\n'   "$CLAUDE_DIR"
    printf '  Symlinks removed: %d\n\n' "$pruned"
    exit 0
fi

# ── Commands: one symlink per .md ───────────────────────────────────────────
cmd_total=0
for src in "$SRC_COMMANDS"/*.md; do
    link_one "$src" "$DST_COMMANDS/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("$(basename "$src")"); continue ;;
        foreign) skipped_foreign+=("$(basename "$src") -> $(readlink "$dst_last")"); continue ;;
    esac
    cmd_total=$((cmd_total + 1))
done

# ── Skills: one symlink per directory ───────────────────────────────────────
# claude/skills/personal/ is not a skill: its children are, on the personal profile.
skill_srcs=()
for src in "$SRC_SKILLS"/*/; do
    [ "$src" = "$SRC_SKILLS/personal/" ] && continue
    skill_srcs+=("$src")
done
if [ "$IN_PROFILE" = 1 ]; then
    for src in "$SRC_SKILLS"/personal/*/; do skill_srcs+=("$src"); done
fi
skill_total=0
for src in "${skill_srcs[@]}"; do
    src="${src%/}"
    link_one "$src" "$DST_SKILLS/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("$(basename "$src")"); continue ;;
        foreign) skipped_foreign+=("$(basename "$src") -> $(readlink "$dst_last")"); continue ;;
    esac
    skill_total=$((skill_total + 1))
done

# ── Rules: one symlink per .md ──────────────────────────────────────────────
# Behavioural rules load at launch in EVERY session, same as ~/.claude/CLAUDE.md.
# Keeping them here means they are version-controlled and land on a new machine
# with one run of this script.
rule_srcs=("$SRC_RULES"/*.md)
if [ "$IN_PROFILE" = 1 ]; then
    rule_srcs+=("$SRC_RULES"/personal/*.md)
fi
rule_total=0
for src in "${rule_srcs[@]}"; do
    link_one "$src" "$DST_RULES/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("$(basename "$src")"); continue ;;
        foreign) skipped_foreign+=("$(basename "$src") -> $(readlink "$dst_last")"); continue ;;
    esac
    rule_total=$((rule_total + 1))
done

# ── Hooks: one symlink per executable script ────────────────────────────────
# settings.json names a hook as ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/<name>, so a fresh
# config folder needs the links. Data files beside the scripts (.tsv, .txt) and tests/ are
# not linked: scripts reach them from their own, symlink-resolved, folder. hooks/personal/
# is not linked either: a stub in hooks/ forwards to a personal hook there on the personal
# profile only. A link another repo made (cc-statusline's event hook) is a foreign symlink
# and stays.
hook_srcs=()
for src in "$SRC_HOOKS"/*.sh "$SRC_HOOKS"/*.py "$SRC_HOOKS"/*.zsh; do
    [ -f "$src" ] && [ -x "$src" ] && hook_srcs+=("$src")
done
hook_total=0
for src in "${hook_srcs[@]}"; do
    link_one "$src" "$DST_HOOKS/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("hooks/$(basename "$src")"); continue ;;
        foreign) skipped_foreign+=("hooks/$(basename "$src") -> $(readlink "$dst_last")"); continue ;;
    esac
    hook_total=$((hook_total + 1))
done

# Drop links whose source vanished (e.g. a skill renamed rewind → go-back), and
# links into personal/ that the profile does not take.
prune_dir "$DST_COMMANDS" "$SRC_COMMANDS"
prune_dir "$DST_SKILLS"   "$SRC_SKILLS"
prune_dir "$DST_RULES"    "$SRC_RULES"
prune_dir "$DST_HOOKS"    "$SRC_HOOKS"

# ── Shell env: publish this checkout's location ──────────────────────────────
# Written rather than committed: the path differs per machine, so the repo holds
# the shape and the generated file holds the value.
mkdir -p "$ENV_DIR"
cat > "$ENV_FILE.tmp" <<EOF
# Generated by agents-shared/scripts/init-global.sh — do not edit.
# Sourced from ~/.zshrc.base. Re-run init-global.sh after moving the checkout.
export AGENTS_SHARED="$REPO_DIR"
export DEV_ROOT="$DEV_ROOT"
EOF
mv "$ENV_FILE.tmp" "$ENV_FILE"

# Make this config folder selectable with `clo -a NAME`: nothing else creates the accounts
# file, so a second config folder used to sit there with no `clo -a` for it.
if [ "$UNLINK" -eq 0 ] && [ -d "$HOME/.claude" ]; then
    "$SCRIPT_DIR/register-claude-account" "$CLAUDE_DIR" | sed 's/^/  accounts: /' || true
fi

# Claude Code's Bash tool does not read ~/.zshrc.base, so skills that run
# "$AGENTS_SHARED/scripts/…" found it empty. Its settings.json env reaches every
# tool call; the value goes there too, merged into what the file already holds.
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
if [ -f "$SETTINGS_FILE" ] && command -v python3 >/dev/null; then
    python3 - "$SETTINGS_FILE" "$REPO_DIR" <<'PY'
import json, os, shutil, sys
path, repo = sys.argv[1], sys.argv[2]
with open(path) as f:
    text = f.read()
assert text.strip(), f"{path} is empty; not rewriting it"
data = json.loads(text)
env = data.setdefault("env", {})
if env.get("AGENTS_SHARED") != repo:
    env["AGENTS_SHARED"] = repo
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    shutil.copymode(path, tmp)
    os.replace(tmp, path)
PY
fi

# ── Skill groups: the committed default for every group ──────────────────────
# Claude Code loads a group nobody names. claude/skill-groups.json names each one, so a new
# machine or config folder starts with the groups off, as this one is; a key already set is kept.
GROUP_NOTE=""
if command -v python3 >/dev/null; then
    GROUP_NOTE="$(python3 "$SCRIPT_DIR/sync-skill-group-settings.py" --config "$CLAUDE_DIR" --quiet)" ||
        GROUP_NOTE="sync-skill-group-settings.py failed: the group defaults were not written"
fi

# ── Push guard: this public repo's pushes go through githooks/pre-push ────────
# The hook refuses a push whose diffs or messages name an entry of the untracked
# denylist (see its header); another repo opts in with
#   git -C <repo> config core.hooksPath "$AGENTS_SHARED/githooks"
# Setting it globally is the owner's step on a personal machine, never this script's: it
# only prints the line below.
HOOKS_NOTE=""
current_hooks="$(git -C "$REPO_DIR" config --local --get core.hooksPath 2>/dev/null || true)"
if [ -z "$current_hooks" ]; then
    git -C "$REPO_DIR" config --local core.hooksPath githooks
    HOOKS_NOTE="set to githooks"
elif [ "$current_hooks" = githooks ]; then
    HOOKS_NOTE="githooks"
else
    HOOKS_NOTE="left at $current_hooks (not githooks): the push guard is off for this clone"
fi
# This repo's own pre-commit (run by githooks/pre-commit's dispatcher): conflict markers and
# check-skills.zsh gate every commit, since skills are served live from this working tree.
GIT_COMMON="$(git -C "$REPO_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
OWN_HOOKS="$GIT_COMMON/hooks"
if [ -n "$GIT_COMMON" ] && mkdir -p "$OWN_HOOKS"; then
    if [ ! -e "$OWN_HOOKS/pre-commit" ] || [ "$(readlink "$OWN_HOOKS/pre-commit")" = "$REPO_DIR/scripts/pre-commit-check.zsh" ]; then
        ln -sfn "$REPO_DIR/scripts/pre-commit-check.zsh" "$OWN_HOOKS/pre-commit"
        HOOKS_NOTE="$HOOKS_NOTE; pre-commit runs scripts/pre-commit-check.zsh"
    else
        HOOKS_NOTE="$HOOKS_NOTE; $OWN_HOOKS/pre-commit is someone else's, so scripts/pre-commit-check.zsh is not installed"
    fi
fi
DENYLIST="${AGENTS_PUSH_DENYLIST:-${XDG_CONFIG_HOME:-$HOME/.config}/agents-shared/push-denylist.txt}"
GLOBAL_HOOKS="$(git config --global --get core.hooksPath 2>/dev/null || true)"

# ── Summary ─────────────────────────────────────────────────────────────────
printf '\n=== agents-shared global setup complete ===\n'
printf '  Target:   %s\n'                       "$CLAUDE_DIR"
printf '  Profile:  %s\n'                       "${PROFILE:-none (shared content only)}"
printf '  Env file: %s\n'                       "$ENV_FILE"
printf '  Commands: %d linked\n'                "$cmd_total"
printf '  Skills:   %d linked\n'                "$skill_total"
printf '  Rules:    %d linked\n'                "$rule_total"
printf '  Hooks:    %d linked\n'                "$hook_total"
printf '  Git hooks: %s\n'                      "$HOOKS_NOTE"
[ -n "$GROUP_NOTE" ] && printf '  %s\n'         "$GROUP_NOTE"
if [ -z "$GLOBAL_HOOKS" ]; then
    printf '  Global git hooks: not set. On a personal machine the name guard is safe to enable for every repo (it skips private\n'
    printf '    repos and runs each repo'"'"'s own hooks); on a work machine do not, it would run on the employer'"'"'s repos:\n'
    printf '      git config --global core.hooksPath "%s/githooks"\n' "$REPO_DIR"
else
    printf '  Global git hooks: %s\n' "$GLOBAL_HOOKS"
    # A repo with a core.hooksPath of its own never runs the global one, so its pushes skip the
    # name guard without a word; scripts/list-push-guard-bypasses.zsh names the public ones.
    BYPASSES="$(zsh "$REPO_DIR/scripts/list-push-guard-bypasses.zsh" "$DEV_ROOT" || true)"
    if [ -n "$BYPASSES" ]; then
        printf '  Push guard skipped: these repos set their own core.hooksPath, so their pushes are never scanned:\n'
        printf '%s\n' "$BYPASSES" | sed 's/^/      /'
        printf '    point each at %s/githooks (its own hooks then belong in .git/hooks, which githooks/ runs too),\n' "$REPO_DIR"
        printf '    or list its OWNER/NAME in %s if it names denylisted entries on purpose\n' \
            "${AGENTS_PUSH_DENYLIST_EXEMPT:-${XDG_CONFIG_HOME:-$HOME/.config}/agents-shared/push-denylist-exempt.txt}"
    fi
fi
if [ ! -r "$DENYLIST" ]; then
    printf '  Push denylist missing: %s\n' "$DENYLIST"
    printf '    every push from this clone is refused until it exists (shape: githooks/push-denylist.txt.example)\n'
elif ! grep -qE '^[[:space:]]*[^[:space:]#]' "$DENYLIST"; then
    printf '\n  !! WARNING: THE PUSH DENYLIST HAS NO ENTRIES: %s\n' "$DENYLIST"
    printf '  !! Pushes from this clone are checked against nothing. Add one name per line\n'
    printf '  !! (shape: githooks/push-denylist.txt.example); the hook warns on every push until you do.\n\n'
fi
printf '  Changes:  +%d new, ~%d repaired, -%d pruned, -%d out of profile\n' "$linked" "$fixed" "$pruned" "$out_of_profile"
if [ ${#skipped_local[@]} -gt 0 ]; then
    printf '  Local overrides preserved: %s\n' "${skipped_local[*]}"
fi
if [ ${#skipped_foreign[@]} -gt 0 ]; then
    printf '  Name taken by another repo, not linked (rename one of them):\n'
    printf '    %s\n' "${skipped_foreign[@]}"
fi
printf '\n'
