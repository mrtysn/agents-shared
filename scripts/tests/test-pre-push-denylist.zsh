#!/bin/zsh
# DESC: Test githooks/pre-push against throwaway repos: missing, empty and filled denylists
set -uo pipefail

hook=${0:A:h:h:h}/githooks/pre-push
work=$(mktemp -d) || exit 1
trap 'rm -rf -- "$work"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid

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

print "pre-push denylist: $pass passed, $fail failed"
(( fail == 0 ))
