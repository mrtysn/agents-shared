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

`hooks/memory-lint.sh` enforces the two checkable halves — index-line shape and
rule collision — and rejects the write with a reason. Bucket choice is judgment
and stays yours.
