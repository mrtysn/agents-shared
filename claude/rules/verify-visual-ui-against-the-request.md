---
paths:
  - "**/*.html"
  - "**/*.css"
  - "**/*.swift"
  - "**/*.tsx"
  - "**/*.vue"
  - "**/*.scss"
  - "**/*.tscn"
  - "**/*.xib"
---

# Check a visual change against the user's own words

**A change to a window, page or layout the user will look at is not done until you
have looked at a render of it and compared it, requirement by requirement, with what
they asked for.** Tests passing and the code reading right say nothing about whether
the result fits, is where they said, or looks the way they described. This extends
[verify a terminal UI by rendering it](verify-terminal-ui-by-rendering.md) to native
Mac apps and web pages.

## What to do

1. **Write the requirement down first**, in the user's words, one line per thing they
   asked for: "stack them side by side", "fit it, no scroll bars", "Last Seen after
   Directory", "merge into the 2nd row, not the 3rd". Quote, do not paraphrase.
2. **Render it.** A web page: headless Chrome to a PNG in the project's gitignored
   output folder, at a wide and a narrow width. A native Mac app: the repo's own capture
   script if it has one, launched through `quiet-open`
   ([window focus](window-focus.md)); an app the user is iterating on is left running
   with plain `open -g`. Then read the image.
3. **Check each line against the picture.** Say for each: shown, not shown, or wrong.
   Anything not shown or wrong is fixed and rendered again before reporting.
4. **Report what the render showed**, including the lines you could not check. Do not
   report "fixed" on the strength of the code.
5. **Do the unrequested part as little as possible.** Narrowing a window, rounding
   corners, or moving a column nobody mentioned is a change the user did not ask for;
   leave it, or name it and ask.

## Provenance

Oct 13 2026, notebook: a survey of 138 pushback messages ("that is not what I asked",
"why are you…") put 34 in the group where the agent misread or reshaped the request,
most of them visual layout work. cc-statusline on Sep 19 gave five corrections in a
row about one window ("it doesnt even fit", "NOO you added scroll bars", "I asked you
to FIT IT", "no dude NOW LEFT label", "I said stack them side by side, you HID THEM").
