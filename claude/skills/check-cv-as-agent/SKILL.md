---
description: Check how a CV or resume PDF reads to an applicant tracking system and to the AI screener on top of it. Extracts the text with three PDF engines, runs checks that need no knowledge of the CV, then has blind subagents parse each extractor's text and diffs what they understood against the truth. Use when the user asks how ATS or AI agents parse their CV, whether their resume is machine-readable or ATS-safe, to check a CV PDF before applying, or after changing a CV's layout, fonts or export.
argument-hint: [path to the CV PDF]
allowed-tools: Read, Write, Bash, Glob, Grep, Agent
---

# check-cv-as-agent

**CV to check:** $ARGUMENTS

An ATS never sees the rendered page, and neither does the LLM layer that now summarises
and ranks candidates on top of it: both see the string a PDF text extractor recovered. So
the test has two halves. The extractor half finds text that breaks (split letters, spaced
headings, unmapped glyphs, hidden text). The agent half finds what a reader *understands*
from text that looks fine: a company read as a location, bullets attached to the wrong job,
a title swallowed by a parenthetical. Only a blind read finds the second kind.

No score comes out of this. ATS "scores" are vendor heuristics with no shared formula; the
output is a list of fields a machine got wrong, each with its cause.

`$S` below is this skill's folder:
`${AGENTS_SHARED:?run agents-shared/scripts/init-global.sh to set it}/claude/skills/check-cv-as-agent`.

## 1. Find the PDF

The argument, else the newest `*CV*.pdf` or `*[Rr]esume*.pdf` in the working directory
and its root. None, or several equally likely: ask which. Check the PDF that will be
uploaded, not a close cousin: a CV built by a script is rebuilt first when its source is
newer than the PDF.

## 2. Extract and check

    W=$(mktemp -d)/cv-as-agent
    "$S/scripts/read-cv-pdf.py" extract <PDF> --out "$W" [--source <the CV's source folder>]

With `--source` (the data files, a `.docx`, the Markdown it is built from) it refuses a PDF
older than any source file: rebuild it through the repo's own step first, writing the new
PDF where the repo keeps generated copies rather than over a committed one.

It writes `$W/<extractor>.txt` for pdfminer.six, pypdf and pymupdf, and prints each check
with PASS, WARN, FAIL or INFO. uv installs the three libraries on first run; nothing else is
needed. If the repo has a PDF check of its own (a `check-cv-pdf`, an ATS test in CI), run it
too: it knows expected values this generic check does not.

## 3. Write the expected record

`$W/expected.json`, in the shape the script's `--help` gives: name, emails, phones, profile
links, roles (title, company, start, end, the first bullet's opening words), education,
skills. It is the truth the blind reads are scored against, so it never comes from the
extracted text:

- **The CV is generated from data files** (JSON, YAML, a Markdown source): build it from
  those, in the order and the mode the PDF was rendered in.
- **Otherwise**: read the PDF itself with the Read tool, which shows the rendered pages, and
  write down what a person sees.

Before going on, check that the record matches the PDF: a role in the data that the PDF
leaves out (a short mode, a filter) is removed from the record, not reported as lost.

## 4. Blind reads

Four readers, all in one message, each given `references/blind-read-brief.md` verbatim
with `{TEXT_FILE}`, `{EXTRACTOR}` and `{READ_FILE}` (`$W/reads/<reader>.json`) filled in:

- **One per extractor's text.** pypdf matters most: it is the default PDF reader behind
  LlamaIndex's `SimpleDirectoryReader` (LangChain's `PyPDFLoader` is named for it; not
  verified), so a company that feeds uploads to an agent through a framework most likely
  hands it pypdf's string.
- **native**: the PDF itself, opened with the reader's own Read tool, as an agent is when
  the upload is dumped on it directly. Model APIs given a PDF send the extracted text and an
  image of each page (Claude's do), so this reader can see what the text alone loses.

A field the native reader gets right and the pypdf reader gets wrong is lost only by
pipelines that extract text first; wrong in both, it is lost everywhere.
Model `haiku`: screening layers run on small, cheap models, and a reader that is too clever
repairs what a production parser would not. Nothing else goes in the brief: no name, no
expected values, no hint of what step 2 found.

Each reader writes its JSON to `{READ_FILE}` itself, so the record never passes through
this session's context. A file that is missing or not valid JSON is re-asked once from the
same agent, then recorded as a failed read.

## 5. Compare

    "$S/scripts/read-cv-pdf.py" compare --expected "$W/expected.json" "$W"/reads/*.json

Per reader: fields right, and each wrong field with expected and got. A field right in one
reader and wrong in another is the extractor's doing, and the script names those; a field
wrong in all three is the layout's or the wording's. Read each reader's `problems`,
`instructions_seen` and `recruiter_summary` yourself: they are not scored, and the summary
is what a recruiter is shown instead of the CV.

## 6. Report

To the user, in the reply:

1. One line: how many fields each reader got right, and whether anything FAILed.
2. A table of what went wrong: field, what the reader got, which readers, the cause
   (the step 2 check or the text that explains it), and the fix. Take fixes from
   `references/what-breaks-a-parse.md`; a fix not there is stated as a hypothesis.
3. The recruiter summaries, quoted, when they misstate the candidate (wrong seniority,
   wrong current employer, wrong school, wrong dates or years of experience). Check every
   summary against the expected record sentence by sentence: a summary can misstate what
   its own reader parsed correctly, and `compare` does not score summaries. Write each
   misstatement to `$W/summary-notes.json` as `{"<reader>": ["what it says, and what the CV
   says"]}`: the page marks them and lists them with the issues.
4. WARNs from step 2 that no reader tripped over, in one line each: real but unproven.

A known and accepted warning (the repo's docs say so) is named as accepted, not re-raised.
Never edit the CV from here: the report is the deliverable, and a CV is the user's own words.

## 7. The page: what each agent saw

When the user asks for a page, or the run found something wrong, write the HTML page:

    "$S/scripts/read-cv-pdf.py" page --run "$W" --out <FILE>.html --session <this session's id>

It reads `extract.json` and the `compare.json` step 5 saved, and shows, in order: the counts
and the stand-in caveat; every issue (text checks, fields no reader found, fields grouped
with how many readers got them wrong, the summary notes); one card per reader with its
wrong fields and the whole record it parsed; every recruiter summary, marked where it
misstates; then each page as
rendered beside pypdf's text with the check findings marked, the other two extractors below
it; and the problems the readers raised. Images are embedded, so the file stands alone.
Without `project-lifecycle` it writes a plain page with the same sections.

**Where it goes.** The page carries the CV's contact details. Inside a repo it goes in a
folder that repo's `.gitignore` already ignores (`git check-ignore -q <path>` exits 0); if
there is none, ask the user before adding one. Outside a repo, beside the PDF. The script
refuses an `--out` inside a repo that git does not ignore. Never publish it.

Then `project-lifecycle page-check <FILE>.html --shots <dir>`, fix what it finds, look at the
desktop shot, and open the page for the user with `open-app-for-user` or the browser.

## Lessons

| Date | What happened | What now prevents it |
|---|---|---|
| 2026-11-24 | First run: the link check flagged 45 of 48 links as unreadable, all inline company and repo links. | Only account roots (`github.com/<user>`, `linkedin.com/in/<user>`) count as profile links. |
| 2026-11-24 | Readers replied with their JSON, which had to be copied into files by hand. | The brief has each reader write `{READ_FILE}` itself. |
| 2026-11-24 | The brief said `title` is "the job title alone", so every reader dropped Intern and Freelance with nowhere to put them. | Readers fill `employment_type`; a qualifier is flagged only when lost from both. |
| 2026-11-24 | The first page render cut the issues table off at the right edge, and the text column ran far past its page image. | Tables carry `ws-table--wrap`; page text sits in a box capped near the image's height. |
| 2026-11-24 | A second CV scored 15/15 in every reader, yet one summary gave a B.A. to the wrong university and another moved an end date by a year; the page hid both, opening summaries only where a field was wrong. | Every summary is shown and checked against the record; education is matched as degree plus institution. |
| 2026-11-24 | Small-caps employers extract as `NIŞANTAŞI`, which lowercases to a dotted i and would not have matched `Nişantaşı`. | `norm` folds accents and dotless ı before comparing. |
| 2026-11-24 | A Fable review of both runs: the CV run had checked a v3.8 PDF against v3.9 data; an empty SKILLS heading, lost superscripts and an author of "Jane" all passed; a company stored with its department and city passed by substring; the page showed no reader's parsed record. | `extract --source` refuses a stale PDF; checks for empty headings, stray ordinals and an author unlike the name; company must match exactly (else WARN); headline, location, education dates and years scored when expected; fields every reader left empty become notes; cards show each parsed record. |
