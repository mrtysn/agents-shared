# Rescue a window that shows but cannot be raised

**A window that Mission Control or the app's Dock menu lists, but that no click, Dock
pick or "Show All Windows" brings forward, is fixed with `rescue-window <app>`** (the
`tools` repo, in `~/bin`), not by probing it by hand with System Events.

    rescue-window firefox              # one window, or one off-screen window
    rescue-window firefox Gmail        # several windows on screen: part of the title
    rescue-window --pid 4242 firefox   # two copies of the app run

It prints every display's frame and every window's frame (top-left coordinates, main
display at 0,0, each window marked `on:<display>` or `off-screen`, `minimized`,
`fullscreen`), then moves the one window onto the main display and activates the app.
Keep the printed lines: they are the evidence of what was wrong, and the fix destroys
the state.

## Without the tool: the one lever System Events has

The window is either off every display (a frame restored from an old arrangement) or
on a Space of a display that is not being shown. In both cases the fix is a move
**across displays**: `set position of window 1 to {x, y}` on the other display, then
back onto the main one, then `activate`. A move inside one display keeps the window's
Space and changes nothing visible. With one display, a move onto it plus `activate`
is all there is. A fullscreen window has its own Space and cannot be moved.

System Events cannot say which Space a window is on; `defaults read com.apple.spaces`
lists Spaces per display, not window membership, and is written only on change.
Membership needs private CGS calls. Do not promise it.

## Traps

- **Every app reports 0 windows, or elements that are not windows** (an
  `AXApplication`, an `AXScrollArea`) in place of its windows: the Accessibility
  channel is answering wrongly for the moment. Seen for about twenty minutes on
  2026-10-14 while the user was in Mission Control; it cleared by itself. Do not
  relaunch apps for it (a Finder relaunch loses tabs); re-probe after the overlay
  is gone. `CGWindowListCopyWindowInfo` keeps answering correctly throughout.
- A process that is not itself active cannot activate another through
  `NSRunningApplication.activate`; `osascript -e 'tell application id "…" to activate'`
  can.
- A Swift `CFArray` of `AXUIElement` cast straight to `[AXUIElement]` yields wrong
  elements; bridge it as `[AnyObject]` first.

## Provenance

Oct 14 2026, notebook: a Firefox window at `0,1118` (the built-in display, stacked
under the main one, on a Space that was not showing) appeared in Mission Control and
in Firefox's Dock menu, and nothing raised it. The session first told the user to
click it and press Esc ("I said i already did those ugh"), then moved it across
displays by hand, then guessed at the cause. The user: "but this sess wont be open?"
