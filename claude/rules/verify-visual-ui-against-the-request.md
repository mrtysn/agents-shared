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
2. **Render it.** A web page: `project-lifecycle page-check URL|FILE --shots DIR`, which
   renders it at 375 and 1280 px in light and dark and fails on what a person sees at once
   (a hover that moves things, sideways overflow, clipped text, headings out of scale, small
   targets, low contrast); fix every finding. The rules it checks, and the ones only reading
   catches, are web-shared's `DESIGN.md`. A native Mac app: the repo's own capture
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

Provenance: [docs/provenance/verify-visual-ui-against-the-request.md](../../docs/provenance/verify-visual-ui-against-the-request.md).
