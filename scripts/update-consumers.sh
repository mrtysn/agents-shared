#!/usr/bin/env bash
#
# update-consumers.sh — Update the .agents submodule in all consumer repos.
#
# Usage:
#   bash scripts/update-consumers.sh              # update only
#   bash scripts/update-consumers.sh --commit     # update and commit submodule pointer
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONSUMERS_FILE="$AGENTS_DIR/consumers.local"

COMMIT=false
if [[ "${1:-}" == "--commit" ]]; then
    COMMIT=true
fi

if [[ ! -f "$CONSUMERS_FILE" ]]; then
    echo "ERROR: $CONSUMERS_FILE not found."
    echo "Create it with one repo path per line."
    exit 1
fi

updated=()
failed=()
skipped=()
committed=()

while IFS= read -r line || [[ -n "$line" ]]; do
    # skip blank lines and comments
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue

    repo="$line"

    if [[ ! -d "$repo" ]]; then
        failed+=("$repo — directory not found")
        continue
    fi

    if [[ ! -d "$repo/.agents" ]]; then
        skipped+=("$repo — no .agents submodule")
        continue
    fi

    echo "Updating $repo..."

    # Capture current commit before update
    before=$(git -C "$repo/.agents" rev-parse HEAD 2>/dev/null || echo "unknown")

    # Update submodule to latest
    if git -C "$repo" submodule update --remote .agents 2>/dev/null; then
        after=$(git -C "$repo/.agents" rev-parse HEAD 2>/dev/null || echo "unknown")

        if [[ "$before" == "$after" ]]; then
            echo "  Already up to date."
        else
            echo "  Updated: ${before:0:7} -> ${after:0:7}"
            updated+=("$repo")
        fi

        # Re-run init.sh to ensure symlinks are current
        if [[ -f "$repo/.agents/scripts/init.sh" ]]; then
            (cd "$repo" && bash .agents/scripts/init.sh) 2>&1 | sed 's/^/  /'
        fi

        # Optionally commit the submodule pointer change
        if $COMMIT && [[ "$before" != "$after" ]]; then
            if git -C "$repo" add .agents && \
               git -C "$repo" commit -m "update agents-shared submodule"; then
                committed+=("$repo")
                echo "  Committed submodule update."
            else
                echo "  WARNING: commit failed in $repo"
            fi
        fi
    else
        failed+=("$repo — submodule update failed")
    fi

    echo ""
done < "$CONSUMERS_FILE"

# ── Summary ──────────────────────────────────────────────────────────────
echo "=== Update Summary ==="
echo "  Updated:   ${#updated[@]}"
echo "  Failed:    ${#failed[@]}"
echo "  Skipped:   ${#skipped[@]}"

if $COMMIT; then
    echo "  Committed: ${#committed[@]}"
fi

if [[ ${#failed[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${failed[@]}"; do
        echo "  - $f"
    done
fi

if [[ ${#skipped[@]} -gt 0 ]]; then
    echo ""
    echo "Skipped:"
    for s in "${skipped[@]}"; do
        echo "  - $s"
    done
fi

if [[ ${#updated[@]} -gt 0 ]] && ! $COMMIT; then
    echo ""
    echo "Submodule pointers updated but not committed. Run with --commit to auto-commit."
fi
