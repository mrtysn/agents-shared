---
name: big-arrow
description: "Point at something on the human's macOS screen with a big arrow and a sign (\"Click HERE\") using the bigarrow CLI. Use whenever the human has to look at, click, type into or choose a specific spot, button, field, window, tab or menu: show me where, point to it, which button, where do I click, zeig mir wo, guide me through this UI, the human must approve or sign something, or you need the human's hand and they may not be looking at the terminal. Mandatory when it is time-critical: a code that expires, a login or payment page that times out, a build waiting on the human."
license: MIT
allowed-tools: Bash(bigarrow:*)
metadata:
  short-description: "Point at the screen with a big arrow and a sign"
---

# big-arrow

`bigarrow` draws a click-through arrow with a sign, needs no permission and never takes the
focus. Point at the thing itself, a line in the terminal is easy to miss.

Needs bigarrow 0.4.6 or newer. If `bigarrow --version` prints an older one, run
`brew upgrade franzenzenhofer/tap/bigarrow` first: an old binary prints `{{value}}` as plain text.

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
bigarrow start --element "Ghostty" --app "System Settings" --text "Switch this on: Ghostty may record your screen" --say
# watch for the result (page changed, job continued, file appeared), then:
bigarrow stop
```

## Rules

- Open the exact pane or URL yourself, then point at the one control left for the human. Never
  walk them through menus. The human clicks; you point.
- The sign is one full sentence naming the action ("Click Save", never "here"). When the
  click approves, grants, pays, signs, sends or deletes, add what happens: "Click Pay:
  49 EUR to Hetzner". The human decides; the facts go on the sign, not only in the terminal.
- `--say` when the human may not be looking. Time-critical (code expires, page times out, job
  waits): `--color red --say` and say by when: "Enter the 2FA code now, it expires in 60 s".
- Something to paste (a command you may not run, a URL, a code): put it on the sign as
  `{{value}}`. The human sees the value on a copy button (no braces); one click copies all of it
  and the arrow stays. Point at where it goes: "Copy {{sudo xcodebuild -license accept}}
  and paste it here", then check that it was pasted.
- One arrow per step; `bigarrow stop` the moment the step is done. Arrows also end alone: after
  300 s, when your session exits, when the human answers (hook below).
- A click on the sign or shaft, except a copy button, removes the arrow (target clicks pass
  through). A removed arrow was seen: check the result, do not redraw. Skip `--close-button`
  unless asked.

## Targets

| You know | Use |
|---|---|
| A label in a native or Electron app | `--element "Allow" --app "System Settings"` |
| An app or one of its windows | `--window "Safari"` / `--window "Safari:Inbox"` |
| A spot inside a Chrome tab | `--rect x,y,w,h --app "Google Chrome:<tab title>"` |
| A spot in a screenshot | `--at X,Y --app "<App>"` |

Always pass `--app` (or `--window`) for a target inside an app: it is raised first and the arrow
hides while another app covers it. `App:title` matches a window title, else a tab. Coordinates
are global top-left points. Inside a Chrome page `--element` needs Chrome started with
`--force-renderer-accessibility`; otherwise convert `getBoundingClientRect()` to `--rect`
([reference.md](reference.md)). Unsure? `bigarrow elements --app X --match "allow"` or `--dry-run`.

<!-- LOCAL: this machine's window-focus rule -->
**Local rules (override the paragraph above).** The user's window-focus rule forbids a window
becoming the active app unattended, and a hotkey terminal hides the instant another app activates.
`--app` and `--window` raise the app, so: never use the `App:title` form (it raises the window and
selects a tab); use `--app X` only for an app already visible on screen; never raise an app that
is not. Never put the user's name on a sign; write the action only ("Click Save"). Do not add the settings.json hook yourself: hooks
are wired by hand from `hooks/`.
For a picture instead of a live arrow (a report, a verification screenshot, a guide), do not draw
on screen: `capture-mac-window --owner NAME --point X,Y --text "Click Save" OUT.png` captures the
window and pastes the arrow on, with X,Y in the window's own pixels.
<!-- LOCAL END -->

## Errors

Exit 2 bad input, 3 target not found (the message lists what exists), 4 permission missing: run
`bigarrow doctor`. Accessibility (`--element`, `App:title`, `--until-click`) and Screen Recording
(`--window App:title`) belong to the app running your shell (Terminal, Ghostty, VS Code), never
to bigarrow. Open the pane the error names (macOS 27: Accessibility is "Device Control and Data
Access") and point at that app's switch.

More (pane ids, look and timing flags): [reference.md](reference.md).

## Setup once

`~/.claude/settings.json`: `"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "bigarrow stop --hook"}]}]}`
