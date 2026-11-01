# Memory hygiene

Auto-memory lives in `~/.claude/projects/<slug>/memory/`. The index, `MEMORY.md`,
loads into every session in that project; the files load only on recall. Write
for that split.

- **Bucket by subject, not by launch directory.** A fact about `~/dev/finance`
  goes in finance's bucket even when the session started in `notebook`. Create
  the bucket if it is missing.
- **The index line names the topic; the file holds the facts.** No figures,
  dates, currency, third-party names or diagnoses in an index line.
  `— Firefly stack, burn report` recalls as well as the version stating the
  balance, and costs nothing when the topic never comes up.
- **Prohibitions are the exception.** A `type: feedback` entry that forbids
  something keeps the instruction in its index line. It has to fire before the
  mistake, and nobody opens a file to check whether an action is forbidden.
- **Rules come first.** Before writing a memory, check `~/.claude/rules/`. If a
  rule already covers it, write nothing; if the rule is wrong, fix the rule.
- **Ask whether it reaches beyond this project.** A memory loads only in sessions
  launched in its bucket, and there is no user-level auto-memory folder (user scope
  is `~/.claude/rules/` and `~/.claude/CLAUDE.md`). If the fact would change what an
  agent does in any other repo (a habit to stop, a tool to use, a way to answer), it
  is not project memory. Choose its home from
  [choose the fix for a pattern](choose-the-fix-for-a-pattern.md), cheapest first:
  a trigger row when it binds to a tool call, a clause in a rule that already
  loads when it is a style preference, a new rule only when every session needs it,
  a local file when it is private. A rule loads in every session, so it is the
  costly option, not the default.
- **Declare the scope.** A new memory file says `scope: project` under `metadata:`
  once you have decided the fact concerns only this project.

`hooks/memory-lint.sh` enforces the three checkable halves — index-line shape, rule
collision and the scope line — and rejects the write with a reason. Bucket choice
and whether the fact is really project-only stay yours.
