---
description: Open an away stretch: the user is gone for a span and the agent must keep working or arm a wakeup. Runs only when the user types /away.
argument-hint: until HH:MM | for 2h | off
---

The user typed `/away $ARGUMENTS`. A UserPromptSubmit hook (`hooks/open-away-stretch.sh`) has already opened or closed the away stretch for this session; its message is in your context.

- For `until` or `for`: say in one line when the stretch ends and what you will do until then. Carry on with the work you owe. Before ending any turn, arm a waiter on the next thing you owe (ScheduleWakeup at its due time, or a background until-loop on the filed job's end) and read its result when it fires. A Stop hook refuses the end of a turn otherwise. Ask no questions during the stretch; decide and report.
- For `off`: the stretch is closed; carry on as normal.
