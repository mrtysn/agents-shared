#!/usr/bin/env bash
#
# init-global.sh — Make agents-shared commands, skills and rules available in EVERY
# project on this machine by symlinking them into the user-level Claude dirs
# (~/.claude/commands, ~/.claude/skills, ~/.claude/rules) instead of each repo's .claude/.
#
# Idempotent. Re-run after adding, renaming, or removing commands/skills:
#   • new sources are linked
#   • wrong-target symlinks are repaired
#   • orphaned symlinks (source renamed/deleted upstream) are pruned
#   • real local override files (non-symlinks) are left untouched
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

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DST_COMMANDS="$CLAUDE_DIR/commands"
DST_SKILLS="$CLAUDE_DIR/skills"
DST_RULES="$CLAUDE_DIR/rules"

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

linked=0 fixed=0 pruned=0
skipped_local=()
RESULT=""

mkdir -p "$DST_COMMANDS" "$DST_SKILLS" "$DST_RULES"

# link_one <src> <dst> — point dst at src, reporting the outcome in $RESULT:
#   linked   a new symlink was created
#   fixed    a symlink that pointed elsewhere was repaired
#   current  already correct, nothing to do
#   skipped  a real (non-symlink) file is there — a local override; left as-is
link_one() {
    local src="$1" dst="$2"
    if [ -L "$dst" ]; then
        if [ "$(readlink "$dst")" = "$src" ]; then RESULT=current; return; fi
        rm "$dst"; ln -s "$src" "$dst"; RESULT=fixed; return
    fi
    if [ -e "$dst" ]; then RESULT=skipped; return; fi
    ln -s "$src" "$dst"; RESULT=linked
}

# prune_dir <dst_dir> <src_dir> — drop symlinks that point into src_dir but whose
# target no longer exists (renamed/removed upstream). With --unlink, drop every
# symlink into src_dir, tearing down what this script created. Foreign symlinks
# and real files are never touched.
prune_dir() {
    local dst_dir="$1" src_dir="$2" link target
    for link in "$dst_dir"/*; do
        [ -L "$link" ] || continue
        target="$(readlink "$link")"
        case "$target" in "$src_dir"/*) ;; *) continue ;; esac
        if [ "$UNLINK" = 1 ] || [ ! -e "$link" ]; then
            rm "$link"; pruned=$((pruned + 1))
        fi
    done
}

# ── Teardown: remove our symlinks and stop ──────────────────────────────────
if [ "$UNLINK" = 1 ]; then
    prune_dir "$DST_COMMANDS" "$SRC_COMMANDS"
    prune_dir "$DST_SKILLS"   "$SRC_SKILLS"
    prune_dir "$DST_RULES"    "$SRC_RULES"
    [ -f "$ENV_FILE" ] && rm "$ENV_FILE"
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
    esac
    cmd_total=$((cmd_total + 1))
done

# ── Skills: one symlink per directory ───────────────────────────────────────
skill_total=0
for src in "$SRC_SKILLS"/*/; do
    src="${src%/}"
    link_one "$src" "$DST_SKILLS/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("$(basename "$src")"); continue ;;
    esac
    skill_total=$((skill_total + 1))
done

# ── Rules: one symlink per .md ──────────────────────────────────────────────
# Behavioural rules load at launch in EVERY session, same as ~/.claude/CLAUDE.md.
# Keeping them here means they are version-controlled and land on a new machine
# with one run of this script.
rule_total=0
for src in "$SRC_RULES"/*.md; do
    link_one "$src" "$DST_RULES/$(basename "$src")"
    case "$RESULT" in
        linked) linked=$((linked + 1)) ;;
        fixed)  fixed=$((fixed + 1)) ;;
        skipped) skipped_local+=("$(basename "$src")"); continue ;;
    esac
    rule_total=$((rule_total + 1))
done

# Drop links whose source vanished (e.g. a skill renamed rewind → go-back).
prune_dir "$DST_COMMANDS" "$SRC_COMMANDS"
prune_dir "$DST_SKILLS"   "$SRC_SKILLS"
prune_dir "$DST_RULES"    "$SRC_RULES"

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

# ── Summary ─────────────────────────────────────────────────────────────────
printf '\n=== agents-shared global setup complete ===\n'
printf '  Target:   %s\n'                       "$CLAUDE_DIR"
printf '  Env file: %s\n'                       "$ENV_FILE"
printf '  Commands: %d linked\n'                "$cmd_total"
printf '  Skills:   %d linked\n'                "$skill_total"
printf '  Rules:    %d linked\n'                "$rule_total"
printf '  Changes:  +%d new, ~%d repaired, -%d pruned\n' "$linked" "$fixed" "$pruned"
if [ ${#skipped_local[@]} -gt 0 ]; then
    printf '  Local overrides preserved: %s\n' "${skipped_local[*]}"
fi
printf '\n'
