#!/usr/bin/env bash
#
# init-global.sh — Make agents-shared commands and skills available in EVERY
# project on this machine by symlinking them into the user-level Claude dirs
# (~/.claude/commands and ~/.claude/skills) instead of each repo's .claude/.
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

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DST_COMMANDS="$CLAUDE_DIR/commands"
DST_SKILLS="$CLAUDE_DIR/skills"

UNLINK=0
[ "${1:-}" = "--unlink" ] && UNLINK=1

linked=0 fixed=0 pruned=0
skipped_local=()
RESULT=""

mkdir -p "$DST_COMMANDS" "$DST_SKILLS"

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

# Drop links whose source vanished (e.g. a skill renamed rewind → go-back).
prune_dir "$DST_COMMANDS" "$SRC_COMMANDS"
prune_dir "$DST_SKILLS"   "$SRC_SKILLS"

# ── Summary ─────────────────────────────────────────────────────────────────
printf '\n=== agents-shared global setup complete ===\n'
printf '  Target:   %s\n'                       "$CLAUDE_DIR"
printf '  Commands: %d linked\n'                "$cmd_total"
printf '  Skills:   %d linked\n'                "$skill_total"
printf '  Changes:  +%d new, ~%d repaired, -%d pruned\n' "$linked" "$fixed" "$pruned"
if [ ${#skipped_local[@]} -gt 0 ]; then
    printf '  Local overrides preserved: %s\n' "${skipped_local[*]}"
fi
printf '\n'
