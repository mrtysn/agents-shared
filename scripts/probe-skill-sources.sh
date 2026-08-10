#!/bin/zsh
# DESC: Probe every skill directory used by /discover-skills with the same query, to see which still yield results
#
# Sources rot: sites go client-rendered, get bought, or quietly die. This runs each
# source in claude/skills/discover-skills/SKILL.md against identical queries so the
# table there can be re-ranked on evidence rather than memory.
#
# Usage: probe-skill-sources.sh <query> [<query> ...]
#        CODE_SLEEP=7 probe-skill-sources.sh pdf kubernetes godot
#
# Note: deliberately NOT `set -e`. Every line here is a probe, and a probe returning
# nothing is a result, not an error.

set -uo pipefail

REPO_ROOT="${0:A:h:h}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# `gh search code` is rate-limited to ~10 req/min; pace it or later queries read as empty.
CODE_SLEEP="${CODE_SLEEP:-7}"

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '2,12p' "${0:A}" | sed 's/^# \{0,1\}//'
  exit $(( $# == 0 ))
fi

sec() { printf '%-28s ' "$1" }

strip_len() {
  python3 -c "
import re,sys
t=re.sub(r'<script.*?</script>|<style.*?</style>','',sys.stdin.read(),flags=re.S)
print(len(' '.join(re.sub(r'<[^>]+>',' ',t).split())))
"
}

gh_repos() { # $1=query, remaining args passed to gh
  local q="$1"; shift
  gh search repos "$q" "$@" --limit 10 --json fullName,stargazersCount \
    --jq '[.[]|"\(.stargazersCount)★ \(.fullName)"]|"\(length) hits\n    "+join("\n    ")' 2>&1 | head -12
}

gh_code() { # all args passed to gh search code
  gh search code "$@" --limit 10 --json repository \
    --jq '[.[].repository.nameWithOwner]|unique|"\(length) repos\n    "+join("\n    ")' 2>&1 | head -12
  sleep "$CODE_SLEEP"
}

hn() { # $1=query $2=tags
  curl -s "https://hn.algolia.com/api/v1/search?query=$1+claude+skill&tags=$2&hitsPerPage=6" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d['nbHits'],'hits')
for h in d['hits'][:6]:
    t=(h.get('title') or h.get('story_title') or '')[:56]
    u=(h.get('url') or h.get('story_url') or '')[:52]
    print(f'    {h.get(\"points\") or 0:>4}p  {t:56}  {u}')
"
}

ssr() { # $1=url — how much text a direct fetch yields; ~0 means client-rendered
  print -r -- "$(curl -s -L --max-time 20 "$1" | strip_len) chars of text"
}

for Q in "$@"; do
  print -r -- "================ QUERY: $Q ================"

  local installed=(${CLAUDE_DIR}/skills/*(N/) ${REPO_ROOT}/claude/skills/*(N/))
  sec "already installed"
  print -r -- "$(grep -rilm1 "$Q" ${installed} 2>/dev/null | wc -l | tr -d ' ') of ${#installed} installed skills mention it"

  sec "gh repos keyword";            gh_repos "$Q claude skill"
  sec "gh repos topic=claude-skills"; gh_repos "$Q" --topic claude-skills
  sec "gh repos topic=agent-skills";  gh_repos "$Q" --topic agent-skills
  sec "gh code SKILL.md";             gh_code --filename SKILL.md "$Q"
  sec "gh code marketplace.json";     gh_code --filename marketplace.json "$Q"
  sec "anthropics/plugins-official";  gh_code --repo anthropics/claude-plugins-official "$Q"
  sec "anthropics/plugins-community"; gh_code --repo anthropics/claude-plugins-community "$Q"
  sec "anthropics/skills";            gh_code --repo anthropics/skills --filename SKILL.md "$Q"
  sec "HN algolia (story)";           hn "$Q" story
  sec "HN algolia (comment)";         hn "$Q" comment

  # Server-rendered? A near-zero count means the site needs `site:` WebSearch instead.
  sec "claudemarketplaces SSR";  ssr "https://claudemarketplaces.com/search?q=$Q"
  sec "skillsmp SSR";            ssr "https://skillsmp.com/search?q=$Q"
  sec "skills.sh SSR";           ssr "https://skills.sh/?q=$Q"
  sec "claudeskills.info SSR";   ssr "https://claudeskills.info/search?q=$Q"

  print -r -- ""
done
