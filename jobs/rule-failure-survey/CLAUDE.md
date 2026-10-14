# Rule Failure Survey

A job on this Mac kept by launchd, installed by `project-lifecycle install` from
`project-lifecycle.json`: every run reports its result to the receiver and the job heartbeats
at its own schedule, so one that silently stops running raises an alert. Operator guide:
README.md.

- `project-lifecycle test` must pass before a commit; `project-lifecycle install` writes and
  loads the launch agent; `project-lifecycle run` runs the job now, the way the agent would;
  `project-lifecycle status` says whether the loaded agent matches the manifest and what the
  last run did. Never write the plist by hand.
- The script exits non-zero on failure and prints what it did; its output goes to
  `~/Library/Logs/rule-failure-survey.log`.
- No machine-specific paths in the manifest: `{repo}` and `{home}` stand for them.
- Comments state what things are, never history.
