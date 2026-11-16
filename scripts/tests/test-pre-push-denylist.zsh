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
# expect <ok|refused> <label> : push HEAD and compare the outcome
expect() {
  local want=$1 label=$2 got
  if git -C $work/repo push -q origin HEAD:main 2>$work/err; then got=ok; else got=refused; fi
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

print "pre-push denylist: $pass passed, $fail failed"
(( fail == 0 ))
