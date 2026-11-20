# Provenance: Commit atomically as you build

Why [the rule](../../claude/rules/commit-atomically-as-you-build.md) exists.

A month of sessions (Aug 27 – Sep 26 2026): 233 requests to commit across 95
sessions in 20 repos, 157 of them `/stg-msg-cmt`, several with "atomically as you
build" or "why have you not incrementally committed all the parts".

Nov 20 2026: three pushes in one session were refused because other sessions had pushed
first. The owner asked for a standing check of the remote before committing and chose a
fetch-before-commit hook, and a clean `git pull --rebase` of the session's own unpushed
commits in place of "never rebase"; force-push stays forbidden.
