#!/usr/bin/env bash
#
# sync-external-skills.sh — Update third-party skills while preserving local edits.
#
# Model (borrowed from oh-my-zsh's `upgrade_oh_my_zsh_custom`, which git-pulls each
# custom plugin with --autostash so local tweaks survive an upstream update):
#
#   .upstream/       pristine mirror of the last-synced upstream files (the "base")
#   <working files>  what actually runs = base with our local edits applied on top
#   override.patch   auto-generated diff(base -> working); the human-readable record
#                    of every local deviation. Absent when a skill is verbatim.
#
# A sync does a 3-way merge (git merge-file) of upstream's base->HEAD change into the
# working files, so local edits are replayed on top instead of clobbered. A genuine
# conflict is left as markers in the working file and reported — never silently lost.
#
# No cloning: uses `git ls-remote` for the HEAD SHA and raw.githubusercontent for
# file contents, so a huge upstream repo (e.g. anthropics/skills) costs a few GETs.
#
# Which files: source.json's optional "files" array (skill-dir-relative). Defaults
# to ["SKILL.md"]. `.venv/` and other local-only artifacts are never listed, so
# they are never touched.
#
# Usage:
#   bash scripts/sync-external-skills.sh                     # sync all to upstream HEAD
#   bash scripts/sync-external-skills.sh <name>              # sync one
#   bash scripts/sync-external-skills.sh --establish-base [<name>]
#                                                            # (re)build .upstream +
#                                                            # override.patch from the
#                                                            # PINNED commit; do not pull
#                                                            # HEAD, change working files,
#                                                            # or bump source.json.
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILLS_DIR="$AGENTS_DIR/claude/skills"

MODE="sync"
filter=""
for arg in "$@"; do
    case "$arg" in
        --establish-base) MODE="establish" ;;
        *) filter="$arg" ;;
    esac
done

today=$(date +%Y-%m-%d)
updated=(); established=(); skipped=(); failed=(); conflicted=()

raw_url() { echo "https://raw.githubusercontent.com/$1/$2/$3"; }

# fetch <repo> <sha> <upstream_path> <dest> — write upstream file to dest, mkdir -p.
fetch() {
    local dest="$4"
    mkdir -p "$(dirname "$dest")"
    curl -fsSL "$(raw_url "$1" "$2" "$3")" -o "$dest"
}

# regen_patch <skill_dir> <file...> — rewrite override.patch as diff(base -> working).
regen_patch() {
    local skill_dir="$1"; shift
    local base_dir="$skill_dir/.upstream"
    local tmp="$skill_dir/.override.tmp"
    : > "$tmp"
    local f
    for f in "$@"; do
        if [ -f "$base_dir/$f" ] && [ -f "$skill_dir/$f" ] \
           && ! diff -q "$base_dir/$f" "$skill_dir/$f" >/dev/null 2>&1; then
            diff -u -L "a/$f" -L "b/$f" "$base_dir/$f" "$skill_dir/$f" >> "$tmp"
        fi
    done
    if [ -s "$tmp" ]; then
        mv "$tmp" "$skill_dir/override.patch"
    else
        rm -f "$tmp" "$skill_dir/override.patch"
    fi
}

for source_file in "$SKILLS_DIR"/*/source.json; do
    [[ -f "$source_file" ]] || continue
    skill_dir="$(dirname "$source_file")"
    skill_name="$(basename "$skill_dir")"
    [[ -z "$filter" || "$skill_name" == "$filter" ]] || continue

    repo=$(jq -r '.repo' "$source_file")
    path=$(jq -r '.path' "$source_file")
    old_commit=$(jq -r '.commit' "$source_file")
    upstream_dir=$(dirname "$path")
    mapfile -t files < <(jq -r '(.files // ["SKILL.md"])[]' "$source_file")
    base_dir="$skill_dir/.upstream"

    # ── Establish-base mode: rebuild base + patch from the pinned commit ──────
    if [[ "$MODE" == "establish" ]]; then
        echo "Establishing base for $skill_name @ ${old_commit:0:7}..."
        ok=1
        for f in "${files[@]}"; do
            if ! fetch "$repo" "$old_commit" "$upstream_dir/$f" "$base_dir/$f"; then
                failed+=("$skill_name — fetch failed: $f @ ${old_commit:0:7}")
                ok=0; break
            fi
        done
        [[ $ok -eq 1 ]] || continue
        regen_patch "$skill_dir" "${files[@]}"
        if [[ -f "$skill_dir/override.patch" ]]; then
            echo "  local override captured"
        else
            echo "  verbatim (no override)"
        fi
        established+=("$skill_name")
        continue
    fi

    # ── Sync mode: pull upstream HEAD, 3-way merge, preserve local edits ──────
    echo "Syncing $skill_name from $repo..."
    new_commit=$(git ls-remote "https://github.com/$repo.git" HEAD 2>/dev/null | cut -f1)
    if [[ -z "$new_commit" ]]; then
        failed+=("$skill_name — ls-remote failed for $repo")
        continue
    fi

    # Ensure a base exists (bootstrap from the pinned commit on first run).
    if [[ ! -d "$base_dir" ]]; then
        ok=1
        for f in "${files[@]}"; do
            fetch "$repo" "$old_commit" "$upstream_dir/$f" "$base_dir/$f" || { ok=0; break; }
        done
        [[ $ok -eq 1 ]] || { failed+=("$skill_name — base bootstrap failed"); continue; }
    fi

    # Fetch the new upstream files into a temp dir.
    tmp_new=$(mktemp -d)
    ok=1
    for f in "${files[@]}"; do
        if ! fetch "$repo" "$new_commit" "$upstream_dir/$f" "$tmp_new/$f"; then
            failed+=("$skill_name — file not found upstream: $f @ ${new_commit:0:7}")
            ok=0; break
        fi
    done
    if [[ $ok -eq 0 ]]; then rm -rf "$tmp_new"; continue; fi

    if [[ "$old_commit" == "$new_commit" ]]; then
        echo "  Already up to date (${old_commit:0:7})"
        regen_patch "$skill_dir" "${files[@]}"   # keep the patch fresh
        skipped+=("$skill_name")
        rm -rf "$tmp_new"
        continue
    fi

    # 3-way merge upstream's base->new change into each working file.
    conflict=0; conflict_files=()
    for f in "${files[@]}"; do
        work="$skill_dir/$f"; base="$base_dir/$f"; new="$tmp_new/$f"
        if [[ ! -f "$work" ]]; then mkdir -p "$(dirname "$work")"; cp "$new" "$work"; continue; fi
        [[ -f "$base" ]] || cp "$new" "$base"   # no recorded base → assume no local edit
        if ! git merge-file -q \
                -L "local:$f" \
                -L "base@${old_commit:0:7}" \
                -L "upstream@${new_commit:0:7}" \
                "$work" "$base" "$new"; then
            conflict=1; conflict_files+=("$f")
        fi
    done

    if [[ $conflict -eq 1 ]]; then
        echo "  CONFLICT in: ${conflict_files[*]}"
        echo "  Conflict markers left in the working file(s); base NOT advanced."
        echo "  Resolve and re-run, or 'git checkout -- $skill_dir' to abort."
        conflicted+=("$skill_name (${conflict_files[*]})")
        rm -rf "$tmp_new"
        continue
    fi

    # Clean merge: advance base, refresh patch, bump provenance.
    for f in "${files[@]}"; do
        mkdir -p "$(dirname "$base_dir/$f")"
        cp "$tmp_new/$f" "$base_dir/$f"
    done
    regen_patch "$skill_dir" "${files[@]}"
    new_src=$(jq --arg c "$new_commit" --arg d "$today" '.commit=$c | .updated=$d' "$source_file")
    printf '%s\n' "$new_src" > "$source_file"

    echo "  Updated: ${old_commit:0:7} → ${new_commit:0:7}"
    [[ -f "$skill_dir/override.patch" ]] && echo "  (local override preserved)"
    updated+=("$skill_name")
    rm -rf "$tmp_new"
done

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=== Sync Summary ==="
[[ "$MODE" == "establish" ]] && echo "  Base established: ${#established[@]}"
echo "  Updated:    ${#updated[@]}"
echo "  Up to date: ${#skipped[@]}"
echo "  Conflicts:  ${#conflicted[@]}"
echo "  Failed:     ${#failed[@]}"

if [[ ${#conflicted[@]} -gt 0 ]]; then
    echo ""; echo "Conflicts (resolve markers, then re-run):"
    for c in "${conflicted[@]}"; do echo "  - $c"; done
fi
if [[ ${#failed[@]} -gt 0 ]]; then
    echo ""; echo "Failures:"
    for f in "${failed[@]}"; do echo "  - $f"; done
fi
if [[ ${#updated[@]} -gt 0 ]]; then
    echo ""; echo "Skills updated. Review the diff (incl. override.patch) and commit."
fi
