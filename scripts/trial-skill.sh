#!/bin/zsh
# DESC: Install, list, remove, or promote trial skills — temporary skill installs in ~/.claude/skills outside agents-shared management
#
# The skills directory holds two kinds of entries: symlinks into agents-shared
# (the permanent, managed set) and real directories (trials — installed to try
# out, deleted when done, or promoted into agents-shared if they earn their keep).
# init-global.sh never touches real directories, so trials coexist safely.
#
# Each trial carries a .trial.json (repo, path, files, commit, installed,
# last_used, group, pinned) — a superset of the external-skill source.json, so
# `promote` can convert it directly and hand off to sync-external-skills.sh
# --establish-base.
#
# A trial's default fate used to be "live forever", which is the wrong default
# for something defined as temporary: nothing deleted it but the user happening
# to look. Two things fix that without a timer deciding on its own. `last_used`
# is stamped by the Skill PostToolUse hook, so idle age means "unused for N
# days" rather than "installed N days ago"; and `rm` writes provenance to a
# ledger before deleting, so removal costs one command to undo. Staleness is
# surfaced by skills-view.py rather than acted on automatically — the view is
# the pressure to clean up, not a reaper.
#
# Usage:
#   trial-skill.sh install <owner/repo> <path-in-repo> [--name <name>] [--group <g>]
#   trial-skill.sh list [--json]
#   trial-skill.sh rm <name> | --group <g>
#   trial-skill.sh promote <name> | --group <g>
#   trial-skill.sh pin <name> | unpin <name>
#   trial-skill.sh restore <name>
#   trial-skill.sh touch <name>          # hook bookkeeping; stamps last_used
#
# <path-in-repo> is the skill's directory in the upstream repo (or its SKILL.md
# path); every file under that directory is fetched. Name defaults to the
# directory's basename. Pass "." when the repo itself is one skill (SKILL.md at
# the root, the usual shape for a standalone skill) — the whole repo is fetched
# and the name comes from the repo, so meodai/skill.color-expert installs as
# color-expert.

set -euo pipefail

SCRIPT_PATH="${0:A}"
SCRIPT_DIR="${SCRIPT_PATH:h}"
AGENTS_DIR="${SCRIPT_DIR:h}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SKILLS_DST="$CONFIG_DIR/skills"

# Idle days after which a trial is reported stale. Nothing deletes on this —
# it only decides what skills-view.py flags.
STALE_DAYS="${TRIAL_STALE_DAYS:-30}"

# Provenance of removed trials, appended before the files go. This is what makes
# `rm` cheap: the ledger holds repo + commit + file list, so `restore` refetches
# the exact bytes that were deleted.
LEDGER="$CONFIG_DIR/trial-skills-removed.jsonl"

usage() {
    sed -n 's/^# \{0,1\}//p' "$SCRIPT_PATH" | sed -n '/^Usage:/,/^$/p'
    exit "${1:-0}"
}

die() { print -u2 "error: $*"; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is required"; }

today() { date +%Y-%m-%d; }

# Epoch seconds for a YYYY-MM-DD. BSD date (macOS) first, GNU as the fallback so
# this still answers on a Linux box; 0 means unparseable, which callers treat as
# "age unknown" rather than "infinitely old".
to_epoch() {
    date -j -f "%Y-%m-%d" "$1" +%s 2>/dev/null \
        || date -d "$1" +%s 2>/dev/null \
        || print 0
}

# Whole days since a trial was last used, falling back to its install date for
# trials that predate last_used. -1 when the date will not parse.
idle_days() {
    local meta="$1" stamp then now
    stamp=$(jq -r '.last_used // .installed // empty' "$meta")
    [[ -n "$stamp" ]] || { print -- -1; return; }
    then=$(to_epoch "$stamp")
    (( then == 0 )) && { print -- -1; return; }
    now=$(date +%s)
    print $(( (now - then) / 86400 ))
}

# Bytes of YAML frontmatter in a SKILL.md. Every skill's name and description
# are loaded into the system prompt of every session on this machine, so this is
# the one cost a skill charges whether or not it is ever invoked — the number
# the view exists to make visible.
frontmatter_chars() {
    local skill_md="$1"
    [[ -f "$skill_md" ]] || { print 0; return; }
    awk '/^---$/{c++; next} c==1{print}' "$skill_md" | wc -c | tr -d ' '
}

# Trial directories belonging to a group, newline-separated. A group is how one
# upstream repo's set of skills stays one unit: installing eleven skills from
# one commit should not mean eleven separate decisions later.
group_members() {
    local g="$1" d
    for d in "$SKILLS_DST"/*(N/); do
        [[ -f "$d/.trial.json" ]] || continue
        [[ "$(jq -r '.group // empty' "$d/.trial.json")" == "$g" ]] && print -r -- "$d"
    done
}

# Fetch every file of a skill at one commit. Shared by install and restore so a
# restored trial is byte-identical to what was removed rather than whatever HEAD
# has drifted to since.
fetch_skill() {
    local repo="$1" sha="$2" skill_path="$3" dst="$4"; shift 4
    local files=("$@") f
    mkdir -p "$dst"
    for f in "${files[@]}"; do
        print "  fetching $f"
        mkdir -p "${dst}/${f:h}"
        if ! curl -fsSL "https://raw.githubusercontent.com/$repo/$sha/$skill_path/$f" -o "$dst/$f"; then
            rm -rf "$dst"
            die "fetch failed: $f — nothing installed"
        fi
    done
}

# ── install ──────────────────────────────────────────────────────────────────
cmd_install() {
    need curl; need jq; need git
    local repo="" repo_path="" name="" group=""
    while (( $# )); do
        case "$1" in
            --name) name="${2:?--name needs a value}"; shift 2 ;;
            --group) group="${2:?--group needs a value}"; shift 2 ;;
            -*) die "unknown flag: $1" ;;
            *) if [[ -z "$repo" ]]; then repo="$1"; else repo_path="$1"; fi; shift ;;
        esac
    done
    [[ -n "$repo" && -n "$repo_path" ]] || usage 1
    [[ "$repo" == */* ]] || die "repo must be owner/repo, got: $repo"

    # Accept the skill directory, its SKILL.md path, or "." when the repo *is*
    # one skill (SKILL.md at the root). That last shape is how standalone skills
    # are published — only a repo collecting many of them puts each in its own
    # subdirectory — and rejecting it turned every one of them away.
    local skill_path="$repo_path"
    [[ "$repo_path" == *.md ]] && skill_path="${repo_path:h}"
    skill_path="${skill_path%/}"
    [[ -n "$skill_path" ]] || die "path must name a skill directory, or '.' for a whole-repo skill"

    # Prefix the tree listing filters on; empty means the whole repo.
    local prefix="$skill_path/"
    if [[ "$skill_path" == "." ]]; then
        prefix=""
        # No directory to take a name from, so use the repo's own, minus the
        # decoration people put on a single-skill repo: meodai/skill.color-expert
        # installs as color-expert.
        if [[ -z "$name" ]]; then
            name="${repo:t}"
            name="${name#skill.}"
            name="${name#skill-}"
            name="${name%-skill}"
        fi
    fi
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
        local files=(${(f)"$(print -r -- "$tree_json" | jq -r --arg p "$prefix" \
            '.tree[] | select(.type == "blob" and (.path | startswith($p))) | .path[($p | length):]')"})
    fi
    (( ${#files} )) && [[ -n "${files[1]}" ]] || die "no files found under $skill_path in $repo"
    (( ${files[(Ie)SKILL.md]} )) || die "$skill_path has no SKILL.md — not a skill directory"

    fetch_skill "$repo" "$sha" "$skill_path" "$dst" "${files[@]}"

    # last_used starts at the install date so a trial that is never invoked ages
    # from the moment it arrived, while one that gets used keeps resetting.
    jq -n --arg repo "$repo" --arg path "$skill_path/SKILL.md" --arg commit "$sha" \
          --arg installed "$(today)" --arg group "$group" \
          '{repo: $repo, path: $path, files: $ARGS.positional, commit: $commit,
            installed: $installed, last_used: $installed, pinned: false}
           + (if $group == "" then {} else {group: $group} end)' \
          --args "${files[@]}" > "$dst/.trial.json"

    print "Installed trial skill '$name' (${#files} files) → $dst"
    [[ -n "$group" ]] && print "Group: $group — 'trial-skill.sh rm --group $group' removes the set."
    print "Available as /$name in new sessions. Remove: trial-skill.sh rm $name — keep: trial-skill.sh promote $name"
}

# ── list ─────────────────────────────────────────────────────────────────────
#
# The whole skills directory, not just trials: skills-view.py renders managed
# and trial entries side by side the way the OJ launcher shows every section of
# its library, and a view that could only see half the inventory would misreport
# what a session actually costs.
#
# --json is the view's only data source. Everything it draws comes from here, so
# the view holds no truth of its own and a mutation is always followed by a
# re-list rather than by patching its own state.
emit_json() {
    local d name kind target meta
    for d in "$SKILLS_DST"/*(N@); do
        name="${d:t}"
        target="$(readlink "$d")"
        jq -n --arg name "$name" --arg target "$target" \
              --argjson desc "$(frontmatter_chars "$d/SKILL.md")" \
              --argjson external "$([[ -f "$target/source.json" ]] && print true || print false)" \
              '{name: $name, kind: "managed", target: $target, desc_chars: $desc,
                external: $external, idle_days: null, stale: false, pinned: false}'
    done
    for d in "$SKILLS_DST"/*(N/); do
        name="${d:t}"
        meta="$d/.trial.json"
        if [[ -f "$meta" ]]; then
            jq --arg name "$name" --arg dir "$d" \
               --argjson desc "$(frontmatter_chars "$d/SKILL.md")" \
               --argjson idle "$(idle_days "$meta")" \
               --argjson stale_at "$STALE_DAYS" \
               '{name: $name, kind: "trial", dir: $dir, repo: .repo, commit: .commit,
                 installed: .installed, last_used: (.last_used // .installed),
                 group: (.group // null), pinned: (.pinned // false),
                 files: (.files | length), desc_chars: $desc, idle_days: $idle,
                 stale: ($idle >= $stale_at and (.pinned // false) == false)}' "$meta"
        else
            jq -n --arg name "$name" --arg dir "$d" \
                  --argjson desc "$(frontmatter_chars "$d/SKILL.md")" \
                  '{name: $name, kind: "untracked", dir: $dir, desc_chars: $desc,
                    idle_days: null, stale: false, pinned: false}'
        fi
    done
}

cmd_list() {
    need jq
    local as_json=0
    [[ "${1:-}" == "--json" ]] && as_json=1

    if (( as_json )); then
        emit_json | jq -s --arg config "$CONFIG_DIR" --arg today "$(today)" \
            --argjson stale_at "$STALE_DAYS" \
            '{config_dir: $config, today: $today, stale_days: $stale_at,
              skills: (. | sort_by(.kind, .name))}'
        return 0
    fi

    local dirs=("$SKILLS_DST"/*(N/))
    if (( ! ${#dirs} )); then
        print "No trial skills installed (all entries in $SKILLS_DST are managed symlinks)."
        return 0
    fi
    local d name meta idle flags
    for d in "${dirs[@]}"; do
        name="${d:t}"
        if [[ -f "$d/.trial.json" ]]; then
            idle=$(idle_days "$d/.trial.json")
            flags=""
            [[ "$(jq -r '.pinned // false' "$d/.trial.json")" == "true" ]] && flags="  [pinned]"
            (( idle >= STALE_DAYS )) && [[ -z "$flags" ]] && flags="  [stale]"
            meta=$(jq -r '"\(.repo)  @ \(.commit[0:7])  installed \(.installed)"' "$d/.trial.json")
            print "$name — $meta  idle ${idle}d$flags"
        else
            print "$name — untracked (no .trial.json; not installed by trial-skill)"
        fi
    done
    print ""
    print "Stale at ${STALE_DAYS}d idle. Full view: skills-view.py"
}

# ── rm ───────────────────────────────────────────────────────────────────────
ledger_append() {
    local meta="$1" name="$2"
    [[ -f "$meta" ]] || return 0
    jq -c --arg name "$name" --arg removed "$(today)" \
       '{name: $name, repo, path, files, commit, installed,
         group: (.group // null), removed: $removed}' "$meta" >> "$LEDGER"
}

remove_one() {
    local dir="$1" name="${1:t}"
    # This is committed code rather than an improvised command, so the delete
    # carries its own check: the target must sit directly under the skills
    # directory and must not be that directory itself.
    [[ "$dir" == "$SKILLS_DST"/* && "$dir" != "$SKILLS_DST" && -n "$name" ]] \
        || die "refusing to remove $dir — not a skill directory under $SKILLS_DST"
    ledger_append "$dir/.trial.json" "$name"
    rm -rf "$dir"
    print "Removed trial skill '$name' ($dir)"
}

cmd_rm() {
    need jq
    if [[ "${1:-}" == "--group" ]]; then
        local g="${2:?--group needs a value}"
        local members=(${(f)"$(group_members "$g")"})
        members=(${members:#})
        (( ${#members} )) || die "no trials in group '$g'"
        local d
        for d in "${members[@]}"; do remove_one "$d"; done
        print "Removed ${#members} trials in group '$g'."
        print "Restore any of them with: trial-skill.sh restore <name>"
        return 0
    fi
    local name="${1:?usage: trial-skill.sh rm <name> | --group <g>}"
    local dst="$SKILLS_DST/$name"
    [[ -L "$dst" ]] && die "$name is a managed skill — remove it from agents-shared instead"
    [[ -d "$dst" ]] || die "no trial skill at $dst"
    remove_one "$dst"
    print "Restore with: trial-skill.sh restore $name"
}

# ── pin / unpin ──────────────────────────────────────────────────────────────
# A pin is a deliberate statement that a trial should stop aging — for something
# you know you want next month but have no reason to promote. It is the honest
# alternative to repeatedly bumping a date to keep the view quiet.
cmd_pin() {
    need jq
    local want="$1"; shift
    local name="${1:?usage: trial-skill.sh pin|unpin <name>}"
    local meta="$SKILLS_DST/$name/.trial.json"
    [[ -f "$meta" ]] || die "no trial skill '$name' at $SKILLS_DST (managed skills do not age)"
    local tmp="$meta.tmp"
    jq --argjson p "$want" '.pinned = $p' "$meta" > "$tmp" && mv "$tmp" "$meta"
    if [[ "$want" == "true" ]]; then
        print "Pinned '$name' — it will not be reported stale."
    else
        print "Unpinned '$name' — it ages from its last use again."
    fi
}

# ── touch ────────────────────────────────────────────────────────────────────
# Called by the Skill PostToolUse hook. This is what makes idle age mean "unused
# for N days" instead of "installed N days ago", so a trial in regular use never
# goes stale. Silent and always successful: it runs inside a tool call, and a
# bookkeeping failure must not surface as one.
cmd_touch() {
    local name="${1:-}"
    [[ -n "$name" ]] || return 0
    local meta="$SKILLS_DST/$name/.trial.json"
    [[ -f "$meta" ]] || return 0
    command -v jq >/dev/null 2>&1 || return 0
    local tmp="$meta.tmp"
    if jq --arg d "$(today)" '.last_used = $d' "$meta" > "$tmp" 2>/dev/null; then
        mv "$tmp" "$meta"
    else
        rm -f "$tmp"
    fi
    return 0
}

# ── restore ──────────────────────────────────────────────────────────────────
cmd_restore() {
    need jq; need curl
    local name="${1:?usage: trial-skill.sh restore <name>}"
    [[ -f "$LEDGER" ]] || die "no ledger at $LEDGER — nothing has been removed yet"
    local entry
    entry=$(jq -c --arg n "$name" 'select(.name == $n)' "$LEDGER" | tail -1)
    [[ -n "$entry" ]] || die "'$name' is not in the ledger — nothing to restore"
    local dst="$SKILLS_DST/$name"
    [[ -e "$dst" ]] && die "$name already exists at $dst"

    local repo sha skill_path
    repo=$(print -r -- "$entry" | jq -r '.repo')
    sha=$(print -r -- "$entry" | jq -r '.commit')
    skill_path=$(print -r -- "$entry" | jq -r '.path | sub("/?SKILL\\.md$"; "")')
    [[ -n "$skill_path" ]] || skill_path="."
    local files=(${(f)"$(print -r -- "$entry" | jq -r '.files[]')"})
    files=(${files:#})
    (( ${#files} )) || die "ledger entry for '$name' records no files"

    print "Restoring '$name' from $repo @ ${sha[1,7]}..."
    fetch_skill "$repo" "$sha" "$skill_path" "$dst" "${files[@]}"
    print -r -- "$entry" | jq --arg today "$(today)" \
        '{repo, path, files, commit, installed, last_used: $today, pinned: false}
         + (if .group == null then {} else {group: .group} end)' > "$dst/.trial.json"
    print "Restored '$name' → $dst (${#files} files, same commit as when removed)"
}

# ── promote ──────────────────────────────────────────────────────────────────
promote_one() {
    local name="$1"
    local src="$SKILLS_DST/$name"
    local dst="$AGENTS_DIR/claude/skills/$name"
    [[ -L "$src" ]] && die "$name is already a managed skill"
    [[ -d "$src" ]] || die "no trial skill at $src"
    [[ -f "$src/.trial.json" ]] || die "$name has no .trial.json — move it into agents-shared by hand"
    [[ -e "$dst" ]] && die "$dst already exists in agents-shared"

    mv "$src" "$dst"
    # last_used, group and pinned are trial bookkeeping; a managed skill does not
    # age, so they are dropped rather than carried into source.json.
    jq '{repo, path, files, commit, updated: .installed}' "$dst/.trial.json" > "$dst/source.json"
    rm "$dst/.trial.json"
    print "Promoted '$name' → $dst (source.json written from trial provenance)"
    "$SCRIPT_DIR/sync-external-skills.sh" --establish-base "$name"
}

cmd_promote() {
    need jq
    local -a names
    if [[ "${1:-}" == "--group" ]]; then
        local g="${2:?--group needs a value}"
        local members=(${(f)"$(group_members "$g")"})
        members=(${members:#})
        (( ${#members} )) || die "no trials in group '$g'"
        local d
        for d in "${members[@]}"; do names+=("${d:t}"); done
    else
        names=("${1:?usage: trial-skill.sh promote <name> | --group <g>}")
    fi

    local n
    for n in "${names[@]}"; do promote_one "$n"; done
    # Once, after the whole set: relinking is idempotent and doing it per skill
    # only makes a group promotion N times slower.
    "$SCRIPT_DIR/init-global.sh"
    print "Done (${#names} promoted). Review and commit in $AGENTS_DIR."
}

# ── dispatch ─────────────────────────────────────────────────────────────────
(( $# )) || usage 1
cmd="$1"; shift
case "$cmd" in
    install) cmd_install "$@" ;;
    list)    cmd_list "$@" ;;
    rm)      cmd_rm "$@" ;;
    promote) cmd_promote "$@" ;;
    pin)     cmd_pin true "$@" ;;
    unpin)   cmd_pin false "$@" ;;
    restore) cmd_restore "$@" ;;
    touch)   cmd_touch "$@" ;;
    -h|--help|help) usage 0 ;;
    *) die "unknown command: $cmd (install | list | rm | promote | pin | unpin | restore | touch)" ;;
esac
