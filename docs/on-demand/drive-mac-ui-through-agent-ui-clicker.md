# Drive Mac UIs through Agent UI Clicker

**To click, read or capture inside a Mac app, use `agent-ui-clicker`, never `osascript` with System
Events, `cliclick` or a bare `screencapture`.** Agent sessions run under tmux, node or Python, and macOS
charges Accessibility and Screen Recording to that chain: the grants are missing, or tied to one build
that the next upgrade breaks. Agent UI Clicker is a menu bar app signed with the local certificate that
holds both grants once; the CLI starts it on demand and hands it the request.

    agent-ui-clicker trusted                                  # both grants on?
    agent-ui-clicker tree "<App>" --depth 8                   # the app's elements, to pick a locator
    agent-ui-clicker click "<App>" "More actions for Emulator" "Open with window"
    agent-ui-clicker key "<App>" escape
    agent-ui-clicker screenshot [--screen main|builtin] ["<App>"]   # PNG paths; read them with Read
    agent-ui-clicker open "<App or file>"                     # background launch, new windows on the Mac's own screen

- **The owner sees every action:** a border round the window, a pill naming the app, and a flash on
  each element before it is pressed. Clicks are Accessibility presses: the mouse does not move and the
  owner's focus stays where it is.
- **Exit 5 means the owner paused agents** (⌃⌥⌘P or Stop on the pill). Stop and tell them; never retry,
  and never fall back to osascript or another route around it.
- **A locator that matches several elements is refused with their list.** Pick a more specific label
  (a tooltip such as "More actions for Emulator" usually is), never a guess.
- An app's own door comes first: ADB Reconnect's devices go through `adb-reconnect device …`, and only
  the app's window goes through this.

Source and rules: `~/dev/agent-ui-clicker` (`CLAUDE.md`, `README.md`).

## Provenance

2026-11-11, adb-reconnect: testing a new menu item needed one click in the app. osascript failed with
"not allowed assistive access"; granting osascript did nothing, because the session's chain is launchd →
Python → node → tmux, and a grant to tmux would break at its next Homebrew upgrade. The owner: "figure
out a way that survives updates", then, when the session said it could not screenshot to check its
work, "we fix the problems at their source … didnt we build this ui driver for that?"
