# Window focus

**Never open a window that becomes the active app unless it went through
`quiet-open`, is an app launched for the user to use, or the user said yes to that
batch.** An app launched for the user goes through plain `open -g`, never
`quiet-open`, which leaves it with no Dock icon and no way to bring it forward.
Reach for a headless mode first; almost nothing an agent runs needs pixels. Where `quiet-open`
is not installed, open a window only with `open -g` (it does not activate the app), on the
non-main display, and only for an app the user is meant to use or after the batch is approved.

**A subagent's brief carries this rule.** A subagent sees no hook line and no
memory of the parent's: a brief for any run that opens, clicks or screenshots a
window says, in the brief itself, that no app may be activated, that windows go on
the non-main display, that no synthetic click or key is sent, and that no menu or
popup is opened (an open menu takes the user's typing without activating anything).
Controls are best tested headlessly, with the window never shown. "The window will
move on your screen" is not that.

The session's focus policy (ALLOW or DENY) is injected at start. The full rule
appears the first time a session launches a window, and covers apps `quiet-open`
cannot quiet, including those whose privacy grant follows their signature.
