# What breaks a parse, and the fix

Causes for the report's table. Each row says which check or which blind-read failure it
explains. Collected from four published resume skills (credited below), cut to what a
check or a blind read can confirm, plus what this skill found on its own.

## Text that breaks in extraction (step 2 finds these)

| Symptom | Cause | Fix |
|---|---|---|
| Almost no text | Image-only or scanned PDF, or text drawn as paths | Export a text-based PDF from the source; never print to image |
| `(cid:12)` codes | A font embedded without a ToUnicode map | Use a font that embeds with one; re-export |
| `E X P E R I E N C E` | CSS `letter-spacing` above about 0.08em; extractors turn tracking into spaces | Track at most 1px at heading size; carry weight with size instead |
| `Ya ş in`, `İ stanbul` | A web font split by `unicode-range` (Google Fonts `latin` / `latin-ext`); the letter comes from a second font resource mid-word | Self-host one font file per weight with no `unicode-range` |
| `notiﬁcation` | Ligatures exported as one glyph (`ﬁ`, `ﬂ`) | `font-variant-ligatures: none` in print CSS |
| Junk where icons were | Icon fonts and emoji for contact labels or bullets | Words for labels (`Email:`), `•` or `-` for bullets |
| A profile link missing from the text | The URL exists only as a link annotation over display text like `LinkedIn` | Show the bare domain path (`linkedin.com/in/name`) as the link's text |
| Text hidden | White, zero-opacity, tiny or off-page text; AI screeners now treat it as keyword stuffing | Remove it; a dark band with white text on it is a false positive |
| Text that addresses an AI | Prompt injection ("ignore previous instructions") | Remove it; screeners flag the application |
| Stray `st`, `th` lines; `Ranked 1 in` | Ordinals set as superscript (`1<sup>st</sup>`) are their own text runs, placed on another line | Plain `1st`, or drop the suffix |
| A section's content after the footer, its heading empty | Side-by-side or floated blocks (two sections in one row); the content stream emits them out of visual order | One section per row in normal flow; the footer last in the source |
| Words fused in one extractor | A line break with no space glyph; content-stream extractors join the lines | Usually cosmetic; worth fixing only when a fused word is a keyword |

## Fields a reader gets wrong (step 4 finds these)

| Reader got | Cause | Fix |
|---|---|---|
| Blank or wrong dates | Year-only range (`2019 – 2022`), seasons, `'21`, or formats mixed across roles | `MM/YYYY` or `Mon YYYY` on every role, one format document-wide |
| Wrong end date on the current role | `Current`, `Now`, `Ongoing` instead of `Present` | `Present` |
| Company blank, or a location as the company | Company and location on one line (`Acme, Remote`) | Employer alone on its line; location on its own or in the contact block |
| A qualifier as the company | Parenthetical on the title line (`Director (Growth)`) reproduces the `Name (Org)` shape | Title alone; the qualifier goes in the headline |
| Title and company swapped or fused | `Title | Company`, `Title — Company`, or a comma in the title (`Engineer, Contract`) | Title and company on separate lines; the qualifier after the dates or in a bullet |
| A lowercase or domain-styled company dropped | `flowly`, `loopwave.io` read as a common word or a URL | Capitalised plain form; a recognised parent in parentheses only if it is a real company name |
| One title for a whole tenure | Several titles stacked in one block | One block per title, each with its dates |
| Bullets under the wrong job | Reading order follows the content stream, not the layout (absolutely positioned list items, columns, tables) | Single column, normal flow; no positioned list items |
| A section missing | A creative heading (`What I've Built`) | `Experience`, `Education`, `Skills`, `Projects`, `Certifications` |
| Degree missing | A bulleted or em-dash-fused education line, or a bare acronym (`MSc`) | Unbulleted; degree spelled out with the acronym; institution on its own line |
| Skill not matched | An acronym never spelled out, or the reverse | Pair them once: `Retrieval-Augmented Generation (RAG)` |
| Wrong years of experience | Overlapping part-time roles counted in full, or year-only dates | Months on every range; mark part-time in the title |
| Contact missing | Contact in a PDF header or footer, which Workday and others drop | Contact in the body, in the first lines |

## What not to chase

- An "ATS score". Each vendor's is a different heuristic; the fields above are what matters.
- Keyword density. Each term once to three times, naturally.
- The "75% of resumes are auto-rejected" figure: it traces to a 2012 vendor pitch with no
  method. Rejection is human, or a knockout question on the form.
- PDF versus DOCX in the abstract. Layout breaks parsers, not the container; follow the
  portal's instruction.

## Sources

- msdanyg/ats-resume-skill (`SKILL.md`, `references/failure-patterns.md`): date, company
  and title-line rules, the plain-text paste test.
- paulo-amaral/ats-resume-optimizer (`references/01-ats-and-formatting.md`,
  `07-myths-and-truth.md`, `src/ats_resume/checks.py`): platform notes, the myths table,
  hidden text and AI screening.
- criblab/ats-resume-builder (`references/ats-parsing.md`): ligatures, links as visible
  text, PDF metadata.
- paramchoudhary/resumeskills (`resume-ats-optimizer`): standard headings; its 75% figure is
  the myth above.
- The tracking, `unicode-range` and positioned-list-item rows were found and fixed on a
  React CV that prints with Chrome, and confirmed with all three extractors.
