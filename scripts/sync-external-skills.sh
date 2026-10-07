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
# One blobless shallow fetch per distinct upstream repo (`--depth=1 --filter=blob:none`):
# trees only, no file contents. Each vendored file's upstream blob SHA is compared with
# the SHA of its `.upstream/` copy locally, so only files that really changed are
# downloaded, and a repo shared by thirty skills costs one fetch, not thirty. A skill
# whose files are all identical is "up to date" even when the repo's HEAD moved, and
# its pin is left alone. The same tree is compared with source.json's `files` list, so
# files added upstream are reported, and a listed file deleted upstream stops that skill
# with a clear message instead of a bare fetch error. (--establish-base still reads the pinned commit via
# raw.githubusercontent.)
#
# Which files: source.json's optional "files" array (skill-dir-relative). Defaults
# to ["SKILL.md"]. `.venv/` and other local-only artifacts are never listed, so
# they are never touched.
#
# Usage:
#   bash scripts/sync-external-skills.sh                     # sync all to upstream HEAD
#   bash scripts/sync-external-skills.sh <name>              # sync one skill, or every
#                                                            # skill in a group (<group>
#                                                            # or <group>:<name>)
#   bash scripts/sync-external-skills.sh --dry-run [<name>]  # preview: which skills are
#                                                            # behind upstream, and whether
#                                                            # the 3-way merge would be clean.
#                                                            # Writes nothing in the repo.
#                                                            # One blobless fetch per distinct
#                                                            # repo, plus blobs of changed files.
#   bash scripts/sync-external-skills.sh --adopt-listing <name>
#                                                            # make source.json's `files` match
#                                                            # upstream's skill directory (files
#                                                            # added upstream come in, files
#                                                            # deleted upstream are dropped),
#                                                            # then sync. Needs a name: lists are
#                                                            # often deliberately partial.
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
ADOPT=0
filter=""
for arg in "$@"; do
    case "$arg" in
        --establish-base) MODE="establish" ;;
        --dry-run) MODE="dry" ;;
        --adopt-listing) ADOPT=1 ;;
        *) filter="$arg" ;;
    esac
done
if [[ $ADOPT -eq 1 && -z "$filter" ]]; then
    echo "--adopt-listing needs a skill or group name: file lists are often deliberately partial." >&2
    exit 2
fi

today=$(date +%Y-%m-%d)
updated=(); established=(); skipped=(); failed=(); conflicted=()
behind_clean=(); behind_conflict=(); drift=()
HEAD_CACHE=$(mktemp -d)
trap 'rm -rf "$HEAD_CACHE"' EXIT

# repo_head <repo> — blobless shallow fetch of upstream HEAD, once per distinct repo per
# run, into $HEAD_CACHE/<repo>.git. Prints HEAD's SHA, or nothing on failure.
repo_dir() { echo "$HEAD_CACHE/${1//\//__}.git"; }
repo_head() {
    local rd; rd=$(repo_dir "$1")
    if [[ ! -f "$rd.sha" ]]; then
        git init -q --bare "$rd" \
            && git -C "$rd" remote add origin "https://github.com/$1.git" \
            && git -C "$rd" fetch -q --depth=1 --filter=blob:none --no-tags origin HEAD 2>/dev/null \
            && git -C "$rd" rev-parse FETCH_HEAD > "$rd.sha" \
            || : > "$rd.sha"
    fi
    cat "$rd.sha"
}

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

# Skills live either flat (claude/skills/<name>/) or inside a group plugin
# (claude/skills/<group>/skills/<name>/, or <group>/off/<name>/ when switched off). A filter matches a skill's own name or
# its group's name, so one argument can sync a whole group.
for source_file in "$SKILLS_DIR"/*/source.json "$SKILLS_DIR"/*/skills/*/source.json "$SKILLS_DIR"/*/off/*/source.json; do
    [[ -f "$source_file" ]] || continue
    skill_dir="$(dirname "$source_file")"
    skill_name="$(basename "$skill_dir")"
    group_name=""
    if [[ "$(dirname "$skill_dir")" != "$SKILLS_DIR" ]] && [[ "$(basename "$(dirname "$skill_dir")")" == "skills" || "$(basename "$(dirname "$skill_dir")")" == "off" ]]; then
        group_name="$(basename "$(dirname "$(dirname "$skill_dir")")")"
        skill_name="$group_name:$skill_name"
    fi
    [[ -z "$filter" || "$skill_name" == "$filter" || "${skill_name#*:}" == "$filter" || "$group_name" == "$filter" ]] || continue

    repo=$(jq -r '.repo' "$source_file")
    path=$(jq -r '.path' "$source_file")
    old_commit=$(jq -r '.commit' "$source_file")
    upstream_dir=$(dirname "$path")
    files=()
    while IFS= read -r f; do files+=("$f"); done < <(jq -r '(.files // ["SKILL.md"])[]' "$source_file")
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

    # ── Sync / dry-run: compare blob SHAs locally, fetch only what changed ────
    [[ "$MODE" == "dry" ]] || echo "Syncing $skill_name from $repo..."
    new_commit=$(repo_head "$repo")
    if [[ -z "$new_commit" ]]; then
        failed+=("$skill_name — fetch failed for $repo")
        continue
    fi
    rd=$(repo_dir "$repo")
    up() { [[ "$upstream_dir" == "." ]] && echo "$1" || echo "$upstream_dir/$1"; }

    # Listing drift: files in upstream's skill directory vs source.json's `files`.
    # Skipped for a skill at the repo root, whose directory is the whole repo.
    added=(); removed=()
    if [[ "$upstream_dir" != "." ]]; then
        git -C "$rd" ls-tree -r --name-only "$new_commit" -- "$upstream_dir" 2>/dev/null \
            | sed "s#^$upstream_dir/##" | sort > "$HEAD_CACHE/up.lst"
        printf '%s\n' "${files[@]}" | sort > "$HEAD_CACHE/ours.lst"
        while IFS= read -r f; do [[ -n "$f" ]] && added+=("$f"); done < <(comm -13 "$HEAD_CACHE/ours.lst" "$HEAD_CACHE/up.lst")
        while IFS= read -r f; do [[ -n "$f" ]] && removed+=("$f"); done < <(comm -23 "$HEAD_CACHE/ours.lst" "$HEAD_CACHE/up.lst")
    fi
    if [[ ${#added[@]} -gt 0 || ${#removed[@]} -gt 0 ]]; then
        [[ $ADOPT -eq 1 && "$MODE" == "sync" ]] \
            || drift+=("$skill_name: ${#added[@]} added, ${#removed[@]} removed upstream — +${added[*]:-} -${removed[*]:-}")
        if [[ $ADOPT -eq 1 && "$MODE" == "sync" ]]; then
            for f in ${removed[@]+"${removed[@]}"}; do rm -f "$skill_dir/$f" "$base_dir/$f"; done
            files=(); while IFS= read -r f; do [[ -n "$f" ]] && files+=("$f"); done < "$HEAD_CACHE/up.lst"
            jq --argjson l "$(jq -R . < "$HEAD_CACHE/up.lst" | jq -s .)" '.files=$l' "$source_file" > "$source_file.tmp" \
                && mv "$source_file.tmp" "$source_file"
            echo "  listing adopted: +${#added[@]} -${#removed[@]}"
        elif [[ ${#removed[@]} -gt 0 ]]; then
            failed+=("$skill_name — listed file(s) removed upstream (${removed[0]}${removed[1]+, …}); rerun with --adopt-listing $skill_name")
            continue
        fi
    fi

    # Ensure a base exists (bootstrap from the pinned commit on first run).
    if [[ ! -d "$base_dir" ]]; then
        if [[ "$MODE" == "dry" ]]; then
            failed+=("$skill_name — no .upstream base; run --establish-base")
            continue
        fi
        ok=1
        for f in "${files[@]}"; do
            fetch "$repo" "$old_commit" "$(up "$f")" "$base_dir/$f" || { ok=0; break; }
        done
        [[ $ok -eq 1 ]] || { failed+=("$skill_name — base bootstrap failed"); continue; }
    fi

    # Which listed files differ from the base? SHAs only; no blob is downloaded here.
    changed=(); new_shas=(); ok=1
    for f in "${files[@]}"; do
        new_sha=$(git -C "$rd" rev-parse -q --verify "$new_commit:$(up "$f")" 2>/dev/null)
        if [[ -z "$new_sha" ]]; then
            failed+=("$skill_name — file not found upstream: $f @ ${new_commit:0:7}")
            ok=0; break
        fi
        if [[ ! -f "$base_dir/$f" ]] || [[ "$(git hash-object --no-filters "$base_dir/$f")" != "$new_sha" ]]; then
            changed+=("$f"); new_shas+=("$new_sha")
        fi
    done
    [[ $ok -eq 1 ]] || continue

    if [[ ${#changed[@]} -eq 0 ]]; then
        [[ "$MODE" == "dry" ]] || echo "  Already up to date (files identical to ${old_commit:0:7})"
        [[ "$MODE" == "dry" ]] || regen_patch "$skill_dir" "${files[@]}"   # keep the patch fresh
        skipped+=("$skill_name")
        continue
    fi

    # Download only the changed blobs.
    tmp_new=$(mktemp -d)
    for i in "${!changed[@]}"; do
        f="${changed[$i]}"
        mkdir -p "$(dirname "$tmp_new/$f")"
        git -C "$rd" cat-file blob "${new_shas[$i]}" > "$tmp_new/$f" 2>/dev/null || ok=0
    done
    if [[ $ok -eq 0 ]]; then
        failed+=("$skill_name — blob download failed @ ${new_commit:0:7}")
        rm -rf "$tmp_new"; continue
    fi

    # 3-way merge upstream's base->new change into each changed working file.
    # Dry-run merges a temp copy of the working file, never the real one.
    conflict=0; conflict_files=()
    for f in "${changed[@]}"; do
        work="$skill_dir/$f"; base="$base_dir/$f"; new="$tmp_new/$f"
        if [[ "$MODE" == "dry" ]]; then
            [[ -f "$work" && -f "$base" ]] || continue
            trial="$tmp_new/.trial"; mkdir -p "$(dirname "$trial/$f")"; cp "$work" "$trial/$f"
            git merge-file -q "$trial/$f" "$base" "$new" || { conflict=1; conflict_files+=("$f"); }
            continue
        fi
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

    if [[ "$MODE" == "dry" ]]; then
        if [[ $conflict -eq 1 ]]; then
            echo "  BEHIND  $skill_name (${#changed[@]} changed)  CONFLICT: ${conflict_files[*]}"
            behind_conflict+=("$skill_name (${conflict_files[*]})")
        else
            echo "  BEHIND  $skill_name (${#changed[@]} changed)  merges clean"
            behind_clean+=("$skill_name")
        fi
        rm -rf "$tmp_new"; continue
    fi

    if [[ $conflict -eq 1 ]]; then
        echo "  CONFLICT in: ${conflict_files[*]}"
        echo "  Conflict markers left in the working file(s); base NOT advanced."
        echo "  Resolve and re-run, or 'git checkout -- $skill_dir' to abort."
        conflicted+=("$skill_name (${conflict_files[*]})")
        rm -rf "$tmp_new"
        continue
    fi

    # Clean merge: advance base, refresh patch, bump provenance.
    for f in "${changed[@]}"; do
        mkdir -p "$(dirname "$base_dir/$f")"
        cp "$tmp_new/$f" "$base_dir/$f"
    done
    regen_patch "$skill_dir" "${files[@]}"
    new_src=$(jq --arg c "$new_commit" --arg d "$today" '.commit=$c | .updated=$d' "$source_file")
    printf '%s\n' "$new_src" > "$source_file"

    echo "  Updated: ${old_commit:0:7} → ${new_commit:0:7} (${#changed[@]} file(s))"
    [[ -f "$skill_dir/override.patch" ]] && echo "  (local override preserved)"
    updated+=("$skill_name")
    rm -rf "$tmp_new"
done

print_drift() {
    [[ ${#drift[@]} -gt 0 ]] || return 0
    echo ""; echo "Listing drift (files added/removed upstream vs source.json; adopt with --adopt-listing <name>):"
    local d; for d in "${drift[@]}"; do echo "  - $d"; done
}

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
if [[ "$MODE" == "dry" ]]; then
    echo "=== Dry Run (nothing written) ==="
    echo "  Up to date:        ${#skipped[@]}"
    echo "  Behind, clean:     ${#behind_clean[@]}"
    echo "  Behind, conflict:  ${#behind_conflict[@]}"
    echo "  Failed:            ${#failed[@]}"
    if [[ ${#failed[@]} -gt 0 ]]; then
        echo ""; echo "Failures:"
        for f in "${failed[@]}"; do echo "  - $f"; done
    fi
    print_drift
    exit 0
fi
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
print_drift
