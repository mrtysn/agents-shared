#!/usr/bin/env bash
# standup-collect.sh — Gather git activity across repos for standup generation.
# Outputs structured text for Claude to process into a standup summary.
#
# Usage: standup-collect.sh [date] [repo-list-file]
#   date           — YYYY-MM-DD (default: auto-detect last active day, up to 14 days back)
#   repo-list-file — file with one repo path per line (default: ~/.claude/standup-repos)

set -euo pipefail

REPO_FILE="${2:-$HOME/.claude/standup-repos}"
MAX_UNTRACKED_READ_LINES=40
MAX_UNTRACKED_DIR_FILES=15

# --- Resolve repos ---

if [[ ! -f "$REPO_FILE" ]]; then
    echo "ERROR: Repo list not found at $REPO_FILE"
    exit 1
fi

REPOS=()
while IFS= read -r line; do
    line="${line%%#*}"
    line="$(echo "$line" | xargs)"   # trim whitespace
    line="${line/#\~/$HOME}"
    [[ -z "$line" ]] && continue
    [[ -d "$line/.git" ]] && REPOS+=("$line")
done < "$REPO_FILE"

if [[ ${#REPOS[@]} -eq 0 ]]; then
    echo "ERROR: No valid git repos found in $REPO_FILE"
    exit 1
fi

# --- Date helpers (macOS + Linux) ---

next_day() {
    if date -v+1d &>/dev/null; then
        date -j -f "%Y-%m-%d" -v+1d "$1" "+%Y-%m-%d"
    else
        date -d "$1 + 1 day" "+%Y-%m-%d"
    fi
}

days_ago() {
    if date -v-1d &>/dev/null; then
        date -j -v-"${1}d" "+%Y-%m-%d"
    else
        date -d "today - $1 days" "+%Y-%m-%d"
    fi
}

day_name() {
    if date -v+0d &>/dev/null; then
        date -j -f "%Y-%m-%d" "$1" "+%A" 2>/dev/null
    else
        date -d "$1" "+%A" 2>/dev/null
    fi
}

today=$(date "+%Y-%m-%d")

has_commits_on() {
    local d="$1" nd
    nd=$(next_day "$d")
    for repo in "${REPOS[@]}"; do
        local c
        c=$(git -C "$repo" log --since="${d} 00:00:00" --until="${nd} 00:00:00" --oneline --all 2>/dev/null | wc -l | tr -d ' ')
        [[ "$c" -gt 0 ]] && return 0
    done
    return 1
}

has_uncommitted() {
    for repo in "${REPOS[@]}"; do
        local c
        c=$(git -C "$repo" status --short 2>/dev/null | wc -l | tr -d ' ')
        [[ "$c" -gt 0 ]] && return 0
    done
    return 1
}

# --- Resolve target date ---

if [[ -n "${1:-}" ]]; then
    TARGET_DATE="$1"
else
    TARGET_DATE=""
    for i in $(seq 1 14); do
        candidate=$(days_ago "$i")
        if has_commits_on "$candidate"; then
            TARGET_DATE="$candidate"
            break
        fi
    done

    if [[ -z "$TARGET_DATE" ]]; then
        if has_uncommitted; then
            TARGET_DATE="$today"
        else
            echo "ERROR: No git activity found in the last 14 days across ${#REPOS[@]} repos"
            exit 1
        fi
    fi
fi

NEXT_DAY=$(next_day "$TARGET_DATE")
DAY=$(day_name "$TARGET_DATE")

# --- Output header ---

echo "=== STANDUP DATA ==="
echo "DATE: $TARGET_DATE ($DAY)"
echo "TODAY: $today"
echo "REPOS: ${REPOS[*]}"
echo ""

# --- Per-repo data ---

for repo in "${REPOS[@]}"; do
    repo_name=$(basename "$repo")

    # Quick check: any activity at all?
    commit_count=$(git -C "$repo" log --since="${TARGET_DATE} 00:00:00" --until="${NEXT_DAY} 00:00:00" --oneline --all 2>/dev/null | wc -l | tr -d ' ')
    uncommitted_count=0
    if [[ "$TARGET_DATE" == "$today" ]] || [[ "$TARGET_DATE" == "$(days_ago 1)" ]]; then
        uncommitted_count=$(git -C "$repo" status --short 2>/dev/null | wc -l | tr -d ' ')
    fi

    # Skip repos with zero activity
    [[ "$commit_count" -eq 0 && "$uncommitted_count" -eq 0 ]] && continue

    echo "=== REPO: $repo_name ==="
    echo "PATH: $repo"
    echo ""

    # --- Commits ---
    echo "--- COMMITS ---"
    if [[ "$commit_count" -gt 0 ]]; then
        git -C "$repo" log --since="${TARGET_DATE} 00:00:00" --until="${NEXT_DAY} 00:00:00" --format="%h %s" --all 2>/dev/null
    else
        echo "(none)"
    fi
    echo ""

    # --- Uncommitted work ---
    if [[ "$uncommitted_count" -gt 0 ]]; then
        echo "--- UNCOMMITTED CHANGES ---"

        status_short=$(git -C "$repo" status --short 2>/dev/null || true)
        echo "STATUS:"
        echo "$status_short"
        echo ""

        diff_stat=$(git -C "$repo" diff --stat 2>/dev/null || true)
        if [[ -n "$diff_stat" ]]; then
            echo "DIFF STAT (unstaged):"
            echo "$diff_stat"
            echo ""
        fi

        staged_stat=$(git -C "$repo" diff --cached --stat 2>/dev/null || true)
        if [[ -n "$staged_stat" ]]; then
            echo "DIFF STAT (staged):"
            echo "$staged_stat"
            echo ""
        fi

        # Tracked changes — show diff content for AI context
        has_tracked=$(git -C "$repo" diff --name-only HEAD 2>/dev/null | wc -l | tr -d ' ')
        if [[ "$has_tracked" -gt 0 ]]; then
            echo "DIFF CONTENT (tracked changes):"
            (git -C "$repo" diff HEAD -- . 2>/dev/null || true) | head -200
            echo ""
        fi

        # Untracked files — read contents to understand intent
        untracked=$(echo "$status_short" | grep "^??" | sed 's/^?? //' || true)
        if [[ -n "$untracked" ]]; then
            echo "UNTRACKED FILES CONTENT:"
            while IFS= read -r ufile; do
                [[ -z "$ufile" ]] && continue
                full_path="$repo/$ufile"
                if [[ -d "$full_path" ]]; then
                    echo "  DIR: $ufile/"
                    find "$full_path" -type f -maxdepth 2 2>/dev/null | head -"$MAX_UNTRACKED_DIR_FILES" | while IFS= read -r f; do
                        rel="${f#$repo/}"
                        echo "    FILE: $rel"
                        if file "$f" 2>/dev/null | grep -q text; then
                            echo "    --- content ---"
                            head -"$MAX_UNTRACKED_READ_LINES" "$f" 2>/dev/null || true
                            echo "    --- end ---"
                        fi
                    done
                elif [[ -f "$full_path" ]] && file "$full_path" 2>/dev/null | grep -q text; then
                    echo "  FILE: $ufile"
                    echo "  --- content ---"
                    head -"$MAX_UNTRACKED_READ_LINES" "$full_path" 2>/dev/null || true
                    echo "  --- end ---"
                fi
            done <<< "$untracked"
            echo ""
        fi
    fi

    echo "=== END REPO: $repo_name ==="
    echo ""
done

# --- Log file status ---

echo "=== LOG STATUS ==="
LOG_DIR=".local-logs/standup"
LOG_FILE="$LOG_DIR/${TARGET_DATE}.md"
if [[ -f "$LOG_FILE" ]]; then
    echo "EXISTS: $LOG_FILE"
else
    echo "MISSING: $LOG_FILE"
fi
echo ""

# --- Backfill info ---

echo "=== BACKFILL STATUS ==="
if [[ -d "$LOG_DIR" ]]; then
    existing=$(ls "$LOG_DIR"/*.md 2>/dev/null | xargs -I{} basename {} .md | sort || true)
    if [[ -n "$existing" ]]; then
        earliest=$(echo "$existing" | head -1)
        echo "EARLIEST_LOG: $earliest"
        echo "EXISTING_LOGS:"
        echo "$existing"
    else
        echo "NO_EXISTING_LOGS"
    fi
else
    echo "NO_LOG_DIR"
fi

echo ""
echo "=== END STANDUP DATA ==="
