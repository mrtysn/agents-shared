#!/bin/zsh
# DESC: Test scripts/list-push-guard-bypasses.zsh against throwaway repos: own hooks paths, visibility cache, exempt list
set -uo pipefail

script=${0:A:h:h}/list-push-guard-bypasses.zsh
githooks=${0:A:h:h:h}/githooks
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export XDG_CACHE_HOME=$work/cache AGENTS_PUSH_DENYLIST_EXEMPT=$work/exempt.txt
cache=$work/cache/agents-shared/repo-visibility
mkdir -p $cache $work/root $work/bin
# `gh` is a stub on PATH: no network. It answers true (private) for OWNER/NAME listed in
# $GH_STUB_PRIVATE and fails for any other, which the script reports as unknown.
cat > $work/bin/gh <<'STUB'
#!/bin/zsh
print -r -- "$*" >> $GH_STUB_LOG
for r in ${(s: :)GH_STUB_PRIVATE}; do [[ $2 == repos/$r ]] && { print true; exit 0; }; done
exit 1
STUB
chmod +x $work/bin/gh
export PATH=$work/bin:$PATH GH_STUB_LOG=$work/gh.log GH_STUB_PRIVATE=o/asked-private

# repo <folder> <origin url> [core.hooksPath]
repo() {
  git init -q $work/root/$1
  git -C $work/root/$1 remote add origin $2
  [[ -n ${3:-} ]] && git -C $work/root/$1 config core.hooksPath $3
}
repo own-hooks     git@github.com:o/Own-Hooks.git .githooks
repo uses-guard    https://github.com/o/uses-guard $githooks
repo no-hooks-path git@github.com:o/no-hooks-path.git
repo private-one   git@github.com:o/private-one.git .githooks
repo public-one    git@github-personal:O/public-one .githooks
repo exempt-one    https://github.com/o/exempt-one.git/ .githooks
repo asked-private git@github.com:o/asked-private.git .githooks
print private > $cache/o__private-one
print public > $cache/o__public-one
print '  O/Exempt-One   # names its owner'"'"'s employers on purpose' > $AGENTS_PUSH_DENYLIST_EXEMPT

out=$($script $work/root)
pass=0 fail=0
# want <listed|absent> <label> <line pattern>
want() {
  local found=absent
  print -r -- $out | grep -qE -- $3 && found=listed
  if [[ $found == $1 ]]; then pass=$((pass+1)); else fail=$((fail+1)); print -r -- "FAIL $2: wanted $1"; print -r -- $out; fi
}
want listed "an own hooks path with no cached visibility is listed as unknown" '^own-hooks  o/Own-Hooks  visibility unknown  core.hooksPath=\.githooks$'
want absent "a repo pointed at githooks/ is not listed" '^uses-guard '
want absent "a repo with no hooks path of its own is not listed" '^no-hooks-path '
want absent "a repo cached as private is not listed" '^private-one '
want listed "a repo cached as public says so, across an ssh host alias" '^public-one  O/public-one  public  '
want absent "an exempt repo is not listed, whatever its case or URL form" '^exempt-one '
want absent "a repo gh says is private is not listed" '^asked-private '
[[ $(<$cache/o__asked-private) == private ]] && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL gh's private answer was not cached"; }
grep -q 'repos/o/private-one' $GH_STUB_LOG && { fail=$((fail+1)); print "FAIL a fresh cached answer asked gh again"; } || pass=$((pass+1))

: > $AGENTS_PUSH_DENYLIST_EXEMPT
out=$($script $work/root)
want listed "without the exempt line the same repo is listed" '^exempt-one  o/exempt-one  visibility unknown  '

print -r -- "push guard bypasses: $pass passed, $fail failed"
(( fail == 0 ))
