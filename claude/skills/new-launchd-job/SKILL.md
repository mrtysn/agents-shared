---
description: Start a new scheduled job or always-on worker for this Mac on the project-lifecycle pipeline — a script kept by launchd whose every run reports and heartbeats to the receiver — then create its GitHub repo. Use when the user asks for something to run every N minutes, nightly, weekly, or to keep running in the background.
argument-hint: [job name] [every N seconds | daily at HH:MM | worker]
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Skill
---

# New Launchd Job Skill

Scaffold a job with `project-lifecycle init launchd-job`, prove its script parses and runs,
then hand the directory to `/new-repo`. The templates live in project-lifecycle
(`project_lifecycle/init.py`); this skill only asks what a person must decide and runs the
command. Any agent can run the command without this skill.

A job that belongs to an existing repo (the script is already there) does not need a new
repo: run the same `init` in `<repo>/jobs/<job-name>/`, point `command` at the existing
script with `{repo}/../../scripts/<name>`, and skip `/new-repo`.

## Required inputs (ask if missing)

Ask with AskUserQuestion, in one call, only for what the user will see or type:

1. **Job name** — what the logs, the receiver and Grafana show (`Nightly Pull`). The slug
   (`nightly-pull`), the agent label (`local.nightly-pull`), the script name and the log file
   derive from it.
2. **Schedule** — one of: every N seconds (`--every 21600`), once a day at a time
   (`--daily-at 03:30`), or always running (`--worker`). Recommend from what the user
   described. A weekly or multi-time schedule is edited into the manifest's `calendar`
   after the init (`{"Weekday": 0, "Hour": 20, "Minute": 0}`).

## Steps

1. **Directory**: the current directory if it has none of `project-lifecycle.json`,
   `scripts/<slug>.zsh`, `CLAUDE.md`; otherwise `mkdir` the slug under the current directory
   and `cd` into it. `init` refuses to overwrite and names what is in the way: stop and
   report, never delete.
2. **Scaffold**:

       project-lifecycle init launchd-job --name "<Job Name>" (--every SECONDS | --daily-at HH:MM | --worker) [--tool <slug>]

   Relay the files it wrote: the manifest, `scripts/<slug>.zsh` (placeholder body; exits
   non-zero on failure), `CLAUDE.md`.
3. **Prove it**: `project-lifecycle test` must pass (the script parses), then
   `project-lifecycle run` runs the job once in the foreground, reported and heartbeating,
   and must exit 0. Do not run `install` here: the user installs when the script does its
   real work, with `project-lifecycle install`.
4. **Repo**: invoke `/new-repo` with the Skill tool, passing the slug and a one-line
   description built from the job name and schedule.
5. **Report**: the directory (absolute path), the slug, the file to edit next
   (`scripts/<slug>.zsh`), and the commands `project-lifecycle install` and
   `project-lifecycle status`.

## What the scaffold already does

- `install` writes `~/Library/LaunchAgents/<label>.plist` with the command wrapped in
  `project-lifecycle job <slug> --interval N -- …` and loads it: every run reports its exit
  status and duration to the receiver, and a heartbeat with the job's own interval goes out
  on every run (continuously for a worker). The receiver alerts to Telegram when a job is
  overdue by twice its interval. `uninstall` unloads and removes the agent; `status`
  compares the loaded agent with the manifest.
- No machine-specific paths: `{repo}` and `{home}` in the manifest stand for them, so the
  manifest commits cleanly and installs on any machine.

## Pitfalls

- **Never write or load a plist by hand**, and never `launchctl` the label yourself; the
  driver owns it, and a hand-made agent is state no repo records.
- **A job with `--every` runs once right after `install`** (RunAtLoad), as the old
  hand-written agents did; a `--daily-at` job does not.
- **A one-off `run` for testing sends a real heartbeat**: a job that then never runs again
  alerts after two intervals. Test with `run` only on a job that will be installed, or
  delete its series from VictoriaMetrics afterwards.
