#!/usr/bin/env bash
#
# sync-external-skills.sh — Fetch latest versions of third-party skills from source repos.
#
# Finds all source.json files under claude/skills/, clones the source repo at the
# latest commit, copies the SKILL.md, and updates the commit SHA in source.json.
#
# Usage:
#   bash scripts/sync-external-skills.sh            # sync all external skills
#   bash scripts/sync-external-skills.sh caveman     # sync only the named skill
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_DIR="$AGENTS_DIR/claude/skills"

filter="${1:-}"
updated=()
failed=()
skipped=()

for source_file in "$SKILLS_DIR"/*/source.json; do
    [[ -f "$source_file" ]] || continue

    skill_dir="$(dirname "$source_file")"
    skill_name="$(basename "$skill_dir")"

    # Apply filter if provided
    if [[ -n "$filter" && "$skill_name" != "$filter" ]]; then
        continue
    fi

    repo=$(python3 -c "import json,sys; print(json.load(sys.stdin)['repo'])" < "$source_file")
    path=$(python3 -c "import json,sys; print(json.load(sys.stdin)['path'])" < "$source_file")
    old_commit=$(python3 -c "import json,sys; print(json.load(sys.stdin)['commit'])" < "$source_file")

    echo "Syncing $skill_name from $repo..."

    # Clone into temp dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf '$tmp_dir'" EXIT

    if ! git clone --depth 1 "https://github.com/$repo.git" "$tmp_dir/repo" 2>/dev/null; then
        failed+=("$skill_name — clone failed for $repo")
        rm -rf "$tmp_dir"
        trap - EXIT
        continue
    fi

    new_commit=$(git -C "$tmp_dir/repo" rev-parse HEAD)

    if [[ "$old_commit" == "$new_commit" ]]; then
        echo "  Already up to date (${old_commit:0:7})"
        skipped+=("$skill_name")
        rm -rf "$tmp_dir"
        trap - EXIT
        continue
    fi

    # Copy the skill file
    source_path="$tmp_dir/repo/$path"
    if [[ ! -f "$source_path" ]]; then
        failed+=("$skill_name — file not found at $path in $repo")
        rm -rf "$tmp_dir"
        trap - EXIT
        continue
    fi

    cp "$source_path" "$skill_dir/SKILL.md"

    # Update source.json with new commit and date
    today=$(date +%Y-%m-%d)
    python3 -c "
import json, sys
with open('$source_file', 'r') as f:
    data = json.load(f)
data['commit'] = '$new_commit'
data['updated'] = '$today'
with open('$source_file', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
"

    echo "  Updated: ${old_commit:0:7} → ${new_commit:0:7}"
    updated+=("$skill_name")

    rm -rf "$tmp_dir"
    trap - EXIT
done

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=== Sync Summary ==="
echo "  Updated:   ${#updated[@]}"
echo "  Up to date: ${#skipped[@]}"
echo "  Failed:    ${#failed[@]}"

if [[ ${#failed[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for f in "${failed[@]}"; do
        echo "  - $f"
    done
fi

if [[ ${#updated[@]} -gt 0 ]]; then
    echo ""
    echo "Skills updated. Review changes and commit as needed."
fi
