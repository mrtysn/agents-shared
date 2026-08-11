#!/bin/zsh
# DESC: Install, list, remove, or promote trial skills — temporary skill installs in ~/.claude/skills outside agents-shared management
#
# The skills directory holds two kinds of entries: symlinks into agents-shared
# (the permanent, managed set) and real directories (trials — installed to try
# out, deleted when done, or promoted into agents-shared if they earn their keep).
# init-global.sh never touches real directories, so trials coexist safely.
#
# Each trial carries a .trial.json (repo, path, files, commit, installed) — a
# superset of the external-skill source.json, so `promote` can convert it
# directly and hand off to sync-external-skills.sh --establish-base.
#
# Usage:
#   trial-skill.sh install <owner/repo> <path-in-repo> [--name <name>]
#   trial-skill.sh list
#   trial-skill.sh rm <name>
#   trial-skill.sh promote <name>
#
# <path-in-repo> is the skill's directory in the upstream repo (or its SKILL.md
# path); every file under that directory is fetched. Name defaults to the
# directory's basename.

set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
AGENTS_DIR="${SCRIPT_DIR:h}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DST="$CONFIG_DIR/skills"

usage() {
    sed -n 's/^# \{0,1\}//p' "$SCRIPT_PATH" | sed -n '/^Usage:/,/^$/p'
    exit "${1:-0}"
}

die() { print -u2 "error: $*"; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

# ── install ──────────────────────────────────────────────────────────────────
cmd_install() {
    need curl; need jq; need git
    local repo="" repo_path="" name=""
    while (( $# )); do
        case "$1" in
            --name) name="${2:?--name needs a value}"; shift 2 ;;
            -*) die "unknown flag: $1" ;;
            *) if [[ -z "$repo" ]]; then repo="$1"; else repo_path="$1"; fi; shift ;;
        esac
    done
    [[ -n "$repo" && -n "$repo_path" ]] || usage 1
    [[ "$repo" == */* ]] || die "repo must be owner/repo, got: $repo"

    # Accept either the skill directory or its SKILL.md path.
    local skill_path="$repo_path"
    [[ "$repo_path" == *.md ]] && skill_path="${repo_path:h}"
    skill_path="${skill_path%/}"
    [[ -n "$skill_path" && "$skill_path" != "." ]] || die "path must point at a skill directory inside the repo"
    [[ -z "$name" ]] && name="${skill_path:t}"

    local dst="$SKILLS_DST/$name"
    if [[ -L "$dst" ]]; then
        die "$name is a managed skill (symlink into $(readlink "$dst"))"
    elif [[ -e "$dst" ]]; then
        die "$name already installed at $dst — 'trial-skill.sh rm $name' first"
    fi

    print "Resolving $repo HEAD..."
    local sha
    sha=$(git ls-remote "https://github.com/$repo.git" HEAD | cut -f1)
    [[ -n "$sha" ]] || die "could not resolve HEAD of $repo"

    print "Listing files under $skill_path @ ${sha[1,7]}..."
    local tree_json
    tree_json=$(curl -fsSL "https://api.github.com/repos/$repo/git/trees/$sha?recursive=1") \
        || die "tree listing failed for $repo"
    if [[ "$(print -r -- "$tree_json" | jq -r '.truncated')" == "true" ]]; then
        print -u2 "warning: tree listing truncated by GitHub; falling back to SKILL.md only"
        local files=("SKILL.md")
    else
        local files=(${(f)"$(print -r -- "$tree_json" | jq -r --arg p "$skill_path/" \
            '.tree[] | select(.type == "blob" and (.path | startswith($p))) | .path[($p | length):]')"})
    fi
    (( ${#files} )) && [[ -n "${files[1]}" ]] || die "no files found under $skill_path in $repo"
    (( ${files[(Ie)SKILL.md]} )) || die "$skill_path has no SKILL.md — not a skill directory"

    mkdir -p "$dst"
    local f
    for f in "${files[@]}"; do
        print "  fetching $f"
        mkdir -p "${dst}/${f:h}"
        if ! curl -fsSL "https://raw.githubusercontent.com/$repo/$sha/$skill_path/$f" -o "$dst/$f"; then
            rm -rf "$dst"
            die "fetch failed: $f — nothing installed"
        fi
    done

    jq -n --arg repo "$repo" --arg path "$skill_path/SKILL.md" --arg commit "$sha" \
          --arg installed "$(date +%Y-%m-%d)" \
          '{repo: $repo, path: $path, files: $ARGS.positional, commit: $commit, installed: $installed}' \
          --args "${files[@]}" > "$dst/.trial.json"

    print "Installed trial skill '$name' (${#files} files) → $dst"
    print "Available as /$name in new sessions. Remove: trial-skill.sh rm $name — keep: trial-skill.sh promote $name"
}

# ── list ─────────────────────────────────────────────────────────────────────
cmd_list() {
    local dirs=("$SKILLS_DST"/*(N/))
    if (( ! ${#dirs} )); then
        print "No trial skills installed (all entries in $SKILLS_DST are managed symlinks)."
        return 0
    fi
    local d name meta
    for d in "${dirs[@]}"; do
        name="${d:t}"
        if [[ -f "$d/.trial.json" ]]; then
            meta=$(jq -r '"\(.repo)  @ \(.commit[0:7])  installed \(.installed)"' "$d/.trial.json")
            print "$name — $meta"
        else
            print "$name — untracked (no .trial.json; not installed by trial-skill)"
        fi
    done
}

# ── rm ───────────────────────────────────────────────────────────────────────
cmd_rm() {
    local name="${1:?usage: trial-skill.sh rm <name>}"
    local dst="$SKILLS_DST/$name"
    [[ -L "$dst" ]] && die "$name is a managed skill — remove it from agents-shared instead"
    [[ -d "$dst" ]] || die "no trial skill at $dst"
    rm -rf "$dst"
    print "Removed trial skill '$name' ($dst)"
}

# ── promote ──────────────────────────────────────────────────────────────────
cmd_promote() {
    need jq
    local name="${1:?usage: trial-skill.sh promote <name>}"
    local src="$SKILLS_DST/$name"
    local dst="$AGENTS_DIR/claude/skills/$name"
    [[ -L "$src" ]] && die "$name is already a managed skill"
    [[ -d "$src" ]] || die "no trial skill at $src"
    [[ -f "$src/.trial.json" ]] || die "$name has no .trial.json — move it into agents-shared by hand"
    [[ -e "$dst" ]] && die "$dst already exists in agents-shared"

    mv "$src" "$dst"
    jq '{repo, path, files, commit, updated: .installed}' "$dst/.trial.json" > "$dst/source.json"
    rm "$dst/.trial.json"

    print "Promoted '$name' → $dst (source.json written from trial provenance)"
    "$SCRIPT_DIR/sync-external-skills.sh" --establish-base "$name"
    "$SCRIPT_DIR/init-global.sh"
    print "Done. Review and commit in $AGENTS_DIR."
}

# ── dispatch ─────────────────────────────────────────────────────────────────
(( $# )) || usage 1
cmd="$1"; shift
case "$cmd" in
    install) cmd_install "$@" ;;
    list)    cmd_list ;;
    rm)      cmd_rm "$@" ;;
    promote) cmd_promote "$@" ;;
    -h|--help|help) usage 0 ;;
    *) die "unknown command: $cmd (install | list | rm | promote)" ;;
esac
