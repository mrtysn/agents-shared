# Provenance: Switch a skill group on yourself

Why [the on-demand note](../on-demand/enable-skill-groups.md) exists.

Skill groups are off globally and switched on per repo. From October to November 2026 a survey
of 483 sessions found agents handing that step to the user four times in three sessions, about
once a week: "To use it, switch the `art` group on for this folder in Skill Tree" (Oct 27), a
group reported "installed but switched off for this folder, so none of them can be loaded here
yet" (Nov 13), and an agent that read an off group's skill file directly to get around it
(Nov 11). On Nov 13 the user asked: "the agents shall be able to drive that tool to enable or
load skills or you can load them yourself?"

On Nov 20 a `list-installed-skills` fork reported the `claude plugin enable` command as a step
for the user, and the calling agent relayed it. The user: "doesnt local-repo-skill-tool-job
allow agents to do this on your own?"

The causes: `discover-skills` already said to switch the group on yourself, but only a session
that invoked it saw that. `list-installed-skills` told its fork to "say" the command, which the
fork read as advice to the user. The SessionStart note in `hooks/note-skill-groups-used-here.sh`
told agents to ask the user. Both were reworded so the agent runs the command, and this note
comes up the first time an agent checks or reads skill state.
