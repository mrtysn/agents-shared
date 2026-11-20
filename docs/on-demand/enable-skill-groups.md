# Switch a skill group on yourself

**A skill group that is off in this folder is switched on by the agent, never handed to the user:**

    $AGENTS_SHARED/scripts/enable-skill-group.zsh <group> --reason "<what this work needs it for>"

Run it from the repo. It switches the group on for this repo only (the gitignored
`.claude/settings.local.json`, as Skill Tree's switch does) and records the reason, so an unused group
can be switched off later. It refuses in a repo that commits `.claude/settings.local.json`: ask the
user there. Then end the turn in text asking the user to type `/reload-plugins`, the one step only
they can take; never through AskUserQuestion, whose answer arrives before the command runs. Load the
skill once the reload shows in the conversation.

- Do not read an off group's `SKILL.md` to get around it; switch the group on.
- A group named at session start as unused since an agent switched it on is switched off with
  `--off --reason "…"` unless the work needs it.
- `--list` shows this repo's recorded switches; `scripts/report-skill-group-use.py --repo .` lists
  every group and its state here.

Provenance: [docs/provenance/enable-skill-groups.md](../provenance/enable-skill-groups.md).
