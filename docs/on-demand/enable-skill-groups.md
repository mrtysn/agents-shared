# Switch a skill group on yourself

**A skill group that is off in this folder is switched on by the agent, never handed to the user:**

    claude plugin enable <group>@skills-dir --scope local     # in the repo root

It writes the repo's gitignored `.claude/settings.local.json`, as Skill Tree's switch does. Then
end the turn in text asking the user to type `/reload-plugins`, the one step only they can take;
never through AskUserQuestion, whose answer arrives before the command runs. Load the skill once
the reload shows in the conversation.

- Do not read an off group's `SKILL.md` to get around it; switch the group on.
- `scripts/report-skill-group-use.py --repo .` lists every group and its state here.

Provenance: [docs/provenance/enable-skill-groups.md](../provenance/enable-skill-groups.md).
