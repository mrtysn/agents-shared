#!/bin/zsh
# DESC: Test githooks/pre-push and its chained hooks against throwaway repos: denylists, repo visibility, the repo's own hooks
set -uo pipefail

hook=${0:A:h:h:h}/githooks/pre-push
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid
export AGENTS_PUSH_DENYLIST_EXEMPT=$work/no-exempt.txt   # the machine's own exempt list never leaks in

git init -q --bare $work/remote.git
git init -q -b main $work/repo
git -C $work/repo config core.hooksPath ${hook:h}
git -C $work/repo remote add origin $work/remote.git
print 'base' > $work/repo/a.txt
git -C $work/repo add a.txt && git -C $work/repo commit -qm 'base'

pass=0 fail=0
# expect <ok|refused> <label> [push args] : push (default HEAD:main) and compare the outcome
expect() {
  local want=$1 label=$2 got
  shift 2
  (( $# )) || set -- HEAD:main
  if git -C $work/repo push -q origin "$@" 2>$work/err; then got=ok; else got=refused; fi
  if [[ $got == $want ]]; then pass=$((pass+1)); else
    fail=$((fail+1)); print -r -- "FAIL $label: wanted $want, got $got"; cat $work/err
  fi
}
commit() {  # commit <file> <content> <message>
  print -r -- $2 > $work/repo/$1
  git -C $work/repo add -A && git -C $work/repo commit -qm $3
}
reset_to_remote() { git -C $work/repo reset -q --hard origin/main 2>/dev/null || git -C $work/repo reset -q --hard HEAD~1; }

export AGENTS_PUSH_DENYLIST=$work/absent.txt
expect refused "missing denylist refuses every push"

export AGENTS_PUSH_DENYLIST=$work/list.txt
: > $AGENTS_PUSH_DENYLIST
expect ok "empty denylist allows the push"
grep -q 'CHECKED AGAINST NOTHING' $work/err || { fail=$((fail+1)); print "FAIL empty denylist prints no warning"; }

print -r -- $'# only a comment\n\n   \n' > $AGENTS_PUSH_DENYLIST
commit h.txt 'x' 'add h'
expect ok "comment-only denylist allows the push"
grep -q 'CHECKED AGAINST NOTHING' $work/err || { fail=$((fail+1)); print "FAIL comment-only denylist prints no warning"; }

print -r -- $'# a comment\n\nAcme\nre:sec?ret[- ]client' > $AGENTS_PUSH_DENYLIST
commit b.txt 'nothing to see' 'add b'
expect ok "clean commit passes"

commit c.txt 'built for ACME corp' 'add c'
expect refused "added line naming an entry, any case"
reset_to_remote

commit d.txt 'acmes and acmeville are other words' 'add d'
expect ok "entry matches whole words only"

commit e.txt 'plain' 'work for acme'
expect refused "commit message naming an entry"
reset_to_remote

commit acme-notes.txt 'plain' 'add notes'
expect refused "path naming an entry"
reset_to_remote

commit f.txt 'the secret client' 'add f'
expect refused "re: entry"
reset_to_remote

# A name that is already public and is now removed: the removal goes through.
export AGENTS_PUSH_DENYLIST=$work/empty.txt; : > $AGENTS_PUSH_DENYLIST
commit g.txt 'acme was here' 'add g'; expect ok "setup: push g with no list entries"
export AGENTS_PUSH_DENYLIST=$work/list.txt
commit g.txt 'nobody was here' 'scrub g'
expect ok "removed lines are not checked"

# ---- holes: unknown remote sha, new branches, identities, tags, binaries, the whole tree ----
export AGENTS_PUSH_DENYLIST=$work/list.txt
print -r -- $'Acme\nre:sec?ret[- ]client' > $AGENTS_PUSH_DENYLIST
reset_to_remote

# Another clone moves the remote, so this clone does not know the remote's tip. The old
# hook checked nothing here.
git clone -q -b main $work/remote.git $work/other
git -C $work/other commit -q --allow-empty -m 'elsewhere'
git -C $work/other push -q origin HEAD:main
commit i.txt 'built for acme' 'add i'
commit i.txt 'clean now' 'scrub i'
expect refused "unknown remote sha: an earlier commit in the push is still checked" --force HEAD:main
reset_to_remote
commit j.txt 'clean' 'add j'
expect ok "unknown remote sha: clean commits pass" --force HEAD:main

# A brand-new branch: every commit no remote-tracking ref holds is checked.
git -C $work/repo checkout -q -b feature
commit k.txt 'the secret client' 'add k'
commit k.txt 'clean' 'scrub k'
expect refused "new branch: an earlier commit naming an entry is checked" HEAD:feature
git -C $work/repo checkout -q main
git -C $work/repo branch -q -D feature

# A sha git cannot read is refused, never passed.
bogus=$(print -r -- "refs/heads/x 1111111111111111111111111111111111111111 refs/heads/x $(printf '0%.0s' {1..40})" |
  (cd $work/repo && $hook origin url 2>/dev/null); print $?)
if [[ $bogus == 1 ]]; then pass=$((pass+1)); else fail=$((fail+1)); print "FAIL unreadable local sha: wanted refusal, exit $bogus"; fi

# Author and committer identities.
reset_to_remote
print x > $work/repo/l.txt; git -C $work/repo add -A
GIT_AUTHOR_NAME='Acme Person' git -C $work/repo commit -qm 'add l'
expect refused "author name naming an entry"
reset_to_remote
print x > $work/repo/m.txt; git -C $work/repo add -A
GIT_COMMITTER_EMAIL='me@acme.example' git -C $work/repo commit -qm 'add m'
expect refused "committer email naming an entry"
reset_to_remote

# Annotated tag messages.
git -C $work/repo tag -a -m 'release for acme' v-bad
expect refused "annotated tag message naming an entry" refs/tags/v-bad
git -C $work/repo tag -a -m 'release' v-good
expect ok "clean annotated tag passes" refs/tags/v-good

# A binary file: its diff says only "Binary files differ".
printf '\0\1 the ACME file \0' > $work/repo/n.bin
git -C $work/repo add -A && git -C $work/repo commit -qm 'add n'
expect refused "binary file naming an entry"
git -C $work/repo rm -q n.bin && git -C $work/repo commit -qm 'drop n'
expect refused "binary file added then removed in the same push is still checked"
reset_to_remote

# The tree at the tip: a name already pushed, found when the denylist grows later.
export AGENTS_PUSH_DENYLIST=$work/later.txt; : > $AGENTS_PUSH_DENYLIST
commit o.txt 'Zorbco was here' 'add o'
expect ok "setup: push a name the list does not know yet"
print -r -- 'Zorbco' > $AGENTS_PUSH_DENYLIST
commit p.txt 'clean' 'add p'
expect refused "tree scan finds a name no pushed diff adds"
reset_to_remote
git -C $work/repo rm -q o.txt && git -C $work/repo commit -qm 'drop o'
expect ok "tree clean once the name is gone"

: > $AGENTS_PUSH_DENYLIST
printf '\0 quuxinc \0' > $work/repo/q.bin
git -C $work/repo add -A && git -C $work/repo commit -qm 'add q'
expect ok "setup: push a binary the list does not know yet"
print -r -- 'Quuxinc' > $AGENTS_PUSH_DENYLIST
commit s.txt 'clean' 'add s'
expect refused "tree scan reads a binary file as bytes"
reset_to_remote
git -C $work/repo rm -q q.bin && git -C $work/repo commit -qm 'drop q'
expect ok "tree clean once the binary is gone"

: > $AGENTS_PUSH_DENYLIST
commit quuxinc-t.txt 'plain' 'add t'
expect ok "setup: push a path the list does not know yet"
print -r -- 'Quuxinc' > $AGENTS_PUSH_DENYLIST
commit u.txt 'clean' 'add u'
expect refused "tree scan finds a path naming an entry"

# Binary noise: a short entry spelled by chance between non-word bytes is not a name.
export AGENTS_PUSH_DENYLIST=$work/short.txt; print -r -- 'Qxz' > $AGENTS_PUSH_DENYLIST
printf '\0\1\2Qxz\3\4\0 some bytes \0' > $work/repo/noise.bin
git -C $work/repo add -A && git -C $work/repo commit -qm 'add noise'
expect ok "short entry inside binary noise is not a hit"
printf '\0\1 author Qxz Corp \0' > $work/repo/noise.bin
git -C $work/repo add -A && git -C $work/repo commit -qm 'name in binary text'
expect refused "short entry inside a printable run of a binary is a hit"

# ---- repo visibility: a private github.com remote is not scanned, public and unknown are ----
# `gh` is a stub on PATH: no network. GH_STUB_ANSWER is true (private), false (public) or fail.
mkdir -p $work/bin
cat > $work/bin/gh <<'STUB'
#!/bin/zsh
print -r -- "$*" >> $GH_STUB_LOG
[[ $GH_STUB_ANSWER == (true|false) ]] || exit 1
print $GH_STUB_ANSWER
STUB
chmod +x $work/bin/gh
export GH_STUB_LOG=$work/gh.log XDG_CACHE_HOME=$work/cache
export PATH=$work/bin:$PATH
cache=$work/cache/agents-shared/repo-visibility

export AGENTS_PUSH_DENYLIST=$work/vis.txt; print -r -- 'Acme' > $AGENTS_PUSH_DENYLIST
reset_to_remote
commit v.txt 'built for acme' 'add v'

# direct <url> : run the hook as git would for this push, from the repo, stdin as git sends it
direct() {
  local old=$(git -C $work/repo rev-parse origin/main 2>/dev/null || print -r -- $zero)
  print -r -- "refs/heads/main $(git -C $work/repo rev-parse HEAD) refs/heads/main $old" |
    (cd $work/repo && $hook origin $1 2>$work/err)
}
# check <ok|refused> <label> <url>
check() {
  local want=$1 label=$2 got
  if direct $3; then got=ok; else got=refused; fi
  if [[ $got == $want ]]; then pass=$((pass+1)); else
    fail=$((fail+1)); print -r -- "FAIL $label: wanted $want, got $got"; cat $work/err
  fi
}
gh_calls() { [[ -f $GH_STUB_LOG ]] && wc -l < $GH_STUB_LOG | tr -d ' ' || print 0; }

: > $GH_STUB_LOG
export GH_STUB_ANSWER=true
check ok "private remote passes a commit that names an entry" https://github.com/some-owner/Some-Repo.git
grep -q 'repos/some-owner/Some-Repo' $GH_STUB_LOG || { fail=$((fail+1)); print "FAIL gh was not asked about OWNER/NAME"; }
grep -q 'unknown' $work/err && { fail=$((fail+1)); print "FAIL private remote printed an unknown line"; }
export AGENTS_PUSH_DENYLIST=$work/absent.txt
check ok "private remote passes with the denylist missing" git@github.com:some-owner/Some-Repo.git
[[ $(gh_calls) == 1 ]] && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL private answer was not cached across URL forms (calls: $(gh_calls))"; }
export GH_STUB_ANSWER=false
check refused "missing denylist refuses a push that is scanned" https://github.com/other-owner/new-repo
rm -rf -- $cache
export AGENTS_PUSH_DENYLIST=$work/vis.txt

check refused "public remote is scanned" https://github.com/pub-owner/pub-repo.git
grep -q 'unknown' $work/err && { fail=$((fail+1)); print "FAIL public remote printed an unknown line"; }
export GH_STUB_ANSWER=fail   # the cached answer must stand without asking again
before=$(gh_calls)
check refused "public answer is cached" https://github.com/pub-owner/pub-repo.git
[[ $(gh_calls) == $before ]] && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL cached answer asked gh again"; }

# A cached answer older than 7 days is asked again.
export GH_STUB_ANSWER=true
touch -t 202001010000 $cache/pub-owner__pub-repo
check ok "answer older than 7 days is refreshed" https://github.com/pub-owner/pub-repo.git
[[ $(gh_calls) == $((before+1)) ]] && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL stale cache was not refreshed"; }

export GH_STUB_ANSWER=fail
check refused "gh failing means unknown, which is scanned" https://github.com/new-owner/new-repo.git
grep -q 'visibility .* is unknown' $work/err || { fail=$((fail+1)); print "FAIL unknown visibility printed no line"; cat $work/err; }
check refused "non-GitHub remote is unknown, which is scanned" ssh://git@example.invalid/o/r.git
grep -q 'visibility .* is unknown' $work/err || { fail=$((fail+1)); print "FAIL non-GitHub remote printed no unknown line"; }
PATH=/usr/bin:/bin check refused "gh missing means unknown, which is scanned" https://github.com/gone-owner/gone-repo.git
grep -q 'visibility .* is unknown' $work/err || { fail=$((fail+1)); print "FAIL missing gh printed no unknown line"; }
[[ -e $cache/new-owner__new-repo ]] && { fail=$((fail+1)); print "FAIL an unknown answer was cached"; }
reset_to_remote

# ---- exempt repos: a listed OWNER/NAME is not scanned, and the hook says so ----
export GH_STUB_ANSWER=false   # every remote below is public
export AGENTS_PUSH_DENYLIST_EXEMPT=$work/exempt.txt
print -r -- '# public repos that name denylisted entries on purpose' > $AGENTS_PUSH_DENYLIST_EXEMPT
print -r -- '  cv-owner/CV   # a CV naming its owner'"'"'s employers' >> $AGENTS_PUSH_DENYLIST_EXEMPT
commit e.txt 'built for acme' 'add e'
check ok "exempt public repo passes a commit that names an entry" git@github.com:cv-owner/cv.git
grep -q 'cv-owner/cv is listed in' $work/err || { fail=$((fail+1)); print "FAIL exempt push printed no line"; cat $work/err; }
check ok "exemption matches another URL form and an ssh host alias" git@github-personal:CV-Owner/cv
check ok "exemption matches an https remote" https://github.com/cv-owner/cv/
check refused "a repo not listed is still scanned" https://github.com/cv-owner/other.git
check refused "the same name under another owner is still scanned" https://github.com/other-owner/cv.git
export AGENTS_PUSH_DENYLIST_EXEMPT=$work/absent-exempt.txt
check refused "a missing exempt list exempts nothing" git@github.com:cv-owner/cv.git
export AGENTS_PUSH_DENYLIST_EXEMPT=$work/no-exempt.txt
reset_to_remote

# ---- the repo's own hooks: a global core.hooksPath must not hide .git/hooks ----
own=$work/repo/.git/hooks
export AGENTS_PUSH_DENYLIST=$work/own-list.txt; print -r -- 'Acme' > $AGENTS_PUSH_DENYLIST
export OWN_LOG=$work/own.log
cat > $own/pre-push <<'HOOK'
#!/bin/sh
echo "args: $*" > "$OWN_LOG"
cat >> "$OWN_LOG"
[ -f "$OWN_LOG.refuse" ] && { echo "own hook refuses" >&2; exit 1; }
exit 0
HOOK
chmod +x $own/pre-push
rm -f -- $OWN_LOG $OWN_LOG.refuse
commit w.txt 'clean' 'add w'
expect ok "the repo's own pre-push runs and can pass"
grep -q "^args: origin " $OWN_LOG && grep -q "^HEAD [0-9a-f]\{40\} refs/heads/main " $OWN_LOG &&
  pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL own pre-push got no args or stdin"; cat $OWN_LOG; }
commit x.txt 'clean' 'add x'
touch $OWN_LOG.refuse
expect refused "the repo's own pre-push can refuse"
grep -q 'own hook refuses' $work/err || { fail=$((fail+1)); print "FAIL own hook's refusal not shown"; }
rm -f -- $OWN_LOG
commit y.txt 'built for acme' 'add y'
expect refused "the scan refuses before the repo's own hook runs"
[[ -e $OWN_LOG ]] && { fail=$((fail+1)); print "FAIL own hook ran after a refused scan"; }
export GH_STUB_ANSWER=true
rm -f -- $OWN_LOG
if direct https://github.com/priv-owner/priv-repo.git; then fail=$((fail+1)); print "FAIL own hook's refusal ignored on a private remote"; else pass=$((pass+1)); fi
[[ -e $OWN_LOG ]] || { fail=$((fail+1)); print "FAIL own hook did not run on a private remote"; }
rm -f -- $OWN_LOG.refuse
reset_to_remote

# Other client-side hooks chain through symlinks to chain-hook, with their arguments.
cat > $own/post-commit <<'HOOK'
#!/bin/sh
echo "post-commit ran" > "$OWN_LOG.pc"
HOOK
cat > $own/post-checkout <<'HOOK'
#!/bin/sh
echo "$#" > "$OWN_LOG.co"
HOOK
chmod +x $own/post-commit $own/post-checkout
commit z.txt 'clean' 'add z'
grep -q 'post-commit ran' $OWN_LOG.pc 2>/dev/null && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL post-commit did not chain to the repo's own hook"; }
git -C $work/repo switch -q -c chained
[[ $(<$OWN_LOG.co) == 3 ]] 2>/dev/null && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL post-checkout got the wrong arguments"; }
git -C $work/repo switch -q main
# A failing own hook fails the command that ran it.
print '#!/bin/sh\nexit 1' > $own/commit-msg; chmod +x $own/commit-msg
print x > $work/repo/fail.txt; git -C $work/repo add -A
git -C $work/repo commit -qm 'add fail' 2>/dev/null && { fail=$((fail+1)); print "FAIL a failing own commit-msg hook did not stop the commit"; } || pass=$((pass+1))
rm -f -- $own/commit-msg
git -C $work/repo commit -qm 'add fail' && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL commit failed with no own commit-msg hook"; }
# Every hook name the dispatcher serves is a symlink to it; pre-push is its own script.
for n in pre-commit commit-msg post-merge post-checkout post-commit prepare-commit-msg; do
  [[ -L ${hook:h}/$n && $(readlink ${hook:h}/$n) == chain-hook ]] || { fail=$((fail+1)); print "FAIL githooks/$n is not a symlink to chain-hook"; }
done
[[ ! -L $hook ]] && pass=$((pass+1)) || { fail=$((fail+1)); print "FAIL pre-push must be its own script"; }

print "pre-push denylist: $pass passed, $fail failed"
(( fail == 0 ))
