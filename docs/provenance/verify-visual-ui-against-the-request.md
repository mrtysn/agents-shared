# Provenance: ---

Why [the rule](../../claude/rules/verify-visual-ui-against-the-request.md) exists.

Oct 13 2026, notebook: a survey of 138 pushback messages ("that is not what I asked",
"why are you…") put 34 in the group where the agent misread or reshaped the request,
most of them visual layout work. cc-statusline on Sep 19 gave five corrections in a
row about one window ("it doesnt even fit", "NOO you added scroll bars", "I asked you
to FIT IT", "no dude NOW LEFT label", "I said stack them side by side, you HID THEM").

Nov 13 2026: a redesigned app page passed its renders, yet hovering a file field moved the
page: the shared stylesheet's hover rule set `border`, so a field drawn without one grew by
1.5 px a side. The user: "triggering the hover state on this browse button moves the ui
around. dude … we cannot get basic shit like this wrong anymore". A screenshot cannot show a
hover, so step 2 now runs `page-check`, which hovers and focuses every control and also
measures overflow, clipping, heading scale, target size and contrast. A survey of chat logs
since Sep 11 2026 found about 24 such corrections (layout that jumps on hover or selection,
misalignment, overflow, clipped menus); the rules behind them are web-shared's `DESIGN.md`.
