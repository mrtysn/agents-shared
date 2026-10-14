# Window focus

**Never open a window that becomes the active app unless it went through
`quiet-open`, is an app launched for the user to use, or the user said yes to that
batch.** An app launched for the user goes through plain `open -g`, never
`quiet-open`, which leaves it with no Dock icon and no way to bring it forward.
Reach for a headless mode first; almost nothing an agent runs needs pixels.

The session's focus policy (ALLOW or DENY) is injected at start. The full rule
appears the first time a session launches a window.
