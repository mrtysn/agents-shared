#!/usr/bin/env bash
#
# init.sh — Bootstrap agents-shared submodule and symlinks for any project.
#
# Usage:
#   bash .agents/scripts/init.sh                          # from project with submodule
#   bash ~/dev/oj/.agents/scripts/init.sh                 # from any project directory
#   bash init.sh git@github-personal:mrtysn/agents-shared.git  # custom remote URL
#
set -euo pipefail

DEFAULT_URL="git@github.com:mrtysn/agents-shared.git"
SUBMODULE_URL="${1:-$DEFAULT_URL}"
AGENTS_DIR=".agents"
CLAUDE_DIR=".claude"

created_commands=0
created_skills=0
skipped_local_commands=()
skipped_local_skills=()

# ── Step 1: Ensure submodule exists and is initialized ──────────────────────

if [ ! -d "$AGENTS_DIR" ] || [ -z "$(ls -A "$AGENTS_DIR" 2>/dev/null)" ]; then
    if git config --file .gitmodules --get "submodule.${AGENTS_DIR}.path" &>/dev/null; then
        echo "Initializing existing .agents submodule..."
        git submodule update --init "$AGENTS_DIR"
    else
        echo "Adding .agents submodule from $SUBMODULE_URL..."
        git submodule add "$SUBMODULE_URL" "$AGENTS_DIR"
    fi
fi

# Verify submodule content
if [ ! -d "$AGENTS_DIR/claude/commands" ]; then
    echo "ERROR: $AGENTS_DIR/claude/commands/ not found after init. Submodule may be misconfigured."
    exit 1
fi

# ── Step 2: Symlink commands ────────────────────────────────────────────────

mkdir -p "$CLAUDE_DIR/commands"

# Remove whole-directory symlink if present (legacy pattern)
if [ -L "$CLAUDE_DIR/commands" ]; then
    echo "Removing legacy directory symlink at $CLAUDE_DIR/commands..."
    rm "$CLAUDE_DIR/commands"
    mkdir -p "$CLAUDE_DIR/commands"
fi

for src in "$AGENTS_DIR"/claude/commands/*.md; do
    [ -f "$src" ] || continue
    name="$(basename "$src")"
    target="$CLAUDE_DIR/commands/$name"
    relative="../../.agents/claude/commands/$name"

    if [ -L "$target" ]; then
        existing="$(readlink "$target")"
        if [ "$existing" = "$relative" ]; then
            continue  # correct symlink already exists
        fi
        # wrong symlink — remove and recreate
        rm "$target"
    elif [ -f "$target" ]; then
        skipped_local_commands+=("$name")
        continue  # local override — preserve
    fi

    ln -s "$relative" "$target"
    created_commands=$((created_commands + 1))
done

# ── Step 3: Symlink skills ─────────────────────────────────────────────────

mkdir -p "$CLAUDE_DIR/skills"

if [ -d "$AGENTS_DIR/claude/skills" ]; then
    for src in "$AGENTS_DIR"/claude/skills/*/; do
        [ -d "$src" ] || continue
        name="$(basename "$src")"
        target="$CLAUDE_DIR/skills/$name"
        relative="../../.agents/claude/skills/$name"

        if [ -L "$target" ]; then
            existing="$(readlink "$target")"
            if [ "$existing" = "$relative" ]; then
                continue  # correct symlink already exists
            fi
            rm "$target"
        elif [ -d "$target" ]; then
            skipped_local_skills+=("$name")
            continue  # local override — preserve
        fi

        ln -s "$relative" "$target"
        created_skills=$((created_skills + 1))
    done
fi

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "=== agents-shared setup complete ==="
echo "  Commands symlinked: $created_commands"
echo "  Skills symlinked:   $created_skills"

if [ ${#skipped_local_commands[@]} -gt 0 ]; then
    echo "  Local command overrides preserved: ${skipped_local_commands[*]}"
fi

if [ ${#skipped_local_skills[@]} -gt 0 ]; then
    echo "  Local skill overrides preserved: ${skipped_local_skills[*]}"
fi

echo ""
