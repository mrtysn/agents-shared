"""Port the local details passport from the 3.0.1 local template into 3.1.0 viewer/ sources.

usage: port_viewer.py OLD_LOCAL_TEMPLATE VIEWER_DIR
Each edit asserts its anchor occurs exactly once; files are read first, then replaced.
"""
import sys
from pathlib import Path

old = Path(sys.argv[1]).read_text()
viewer = Path(sys.argv[2])
assert old


def between(text, start, end):
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def edit(name, anchor, insert, before=False):
    p = viewer / name
    text = p.read_text()
    assert text and text.count(anchor) == 1, (name, anchor[:60], text.count(anchor))
    new = text.replace(anchor, insert + anchor if before else anchor + insert)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(new)
    tmp.replace(p)
    print("edited", name)


# CSS: everything from the notes width rule through the meta opacity rule, dedented 4.
css = between(old, '    .focus-chip[data-has-notes="true"] { width:', "    .focus-chip[data-has-notes=\"true\"] .semantic-passport-meta { opacity: 0.72; }")
css += '    .focus-chip[data-has-notes="true"] .semantic-passport-meta { opacity: 0.72; }\n'
css = "".join(line[4:] if line.startswith("    ") else line for line in css.splitlines(keepends=True))
edit("viewer.css", ".semantic-passport-detail[hidden] { display: none; }\n", css)

# Template: data marker and notes markup.
edit("template.source.html", "    <!-- ARCHIFY:SOURCE_EVIDENCE_DATA -->\n", "    <!-- ARCHIFY:DETAILS_DATA -->\n")
markup = between(old, '            <div class="semantic-passport-notes" id="focus-notes"', '            <div class="semantic-passport-meta" id="focus-passport-meta"')
edit("template.source.html", '            <span class="semantic-passport-detail" id="focus-detail" hidden></span>\n', markup)

# Runtime: Archify.details IIFE at the end of motion-governor.js.
iife = between(old, "    /* Authored details on demand.", "    /* Verified repository evidence is emitted")
mg = (viewer / "motion-governor.js").read_text()
assert mg.rstrip().endswith("})();")
tmp = viewer / "motion-governor.js.tmp"
tmp.write_text(mg.rstrip("\n") + "\n" + iife.rstrip("\n") + "\n")
tmp.replace(viewer / "motion-governor.js")
print("edited motion-governor.js")

# focus.js: element lookups, renderNotes/renderRelationshipNotes, and calls.
edit("focus.js", "      var detail = document.getElementById('focus-detail');\n",
     "      var notes = document.getElementById('focus-notes');\n"
     "      var notesEyebrow = document.getElementById('focus-notes-eyebrow');\n"
     "      var notesSummary = document.getElementById('focus-notes-summary');\n"
     "      var notesPoints = document.getElementById('focus-notes-points');\n"
     "      var notesLinks = document.getElementById('focus-notes-links');\n"
     "      var passportNodeId = null;\n")
funcs = between(old, "      function renderNotes(authored, eyebrowText) {", "      function renderPassport(id, node) {")
edit("focus.js", "      function renderPassport(id, node) {\n", funcs, before=True)
edit("focus.js", "      function renderPassport(id, node) {\n",
     "        passportNodeId = id;\n        renderNotes(Archify.details.node(id), '');\n")
edit("focus.js", "        if (options.clearPin === true) {\n          pinnedRelationship = null;\n",
     "", before=False)
p = viewer / "focus.js"
text = p.read_text()
a = "        if (options.clearPin === true) {\n          pinnedRelationship = null;\n          pinnedRelationshipKey = null;\n          svg.removeAttribute('data-relationship-pin-active');\n        }\n"
assert text.count(a) == 1
b = ("        if (options.clearPin === true) {\n"
     "          var hadPin = pinnedRelationshipKey !== null && pinnedRelationshipKey !== undefined;\n"
     "          pinnedRelationship = null;\n          pinnedRelationshipKey = null;\n"
     "          svg.removeAttribute('data-relationship-pin-active');\n"
     "          if (hadPin) renderRelationshipNotes(null);\n        }\n")
text = text.replace(a, b)
c = "        renderRelationshipCopyAction();\n        summary.textContent = viewerText('viewer.passport.relationship.pinned', {\n"
assert text.count(c) == 1, text.count(c)
text = text.replace(c, "        renderRelationshipCopyAction();\n        renderRelationshipNotes(record);\n        summary.textContent = viewerText('viewer.passport.relationship.pinned', {\n")
tmp = p.with_suffix(".js.tmp")
tmp.write_text(text)
tmp.replace(p)
print("edited focus.js pin hooks")
