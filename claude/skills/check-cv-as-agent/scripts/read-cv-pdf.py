#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pypdf>=5", "pdfminer.six>=20231228", "pymupdf>=1.24"]
# ///
# DESC: Extract a CV PDF the way ATS parsers and AI screeners receive it, check the text, and diff blind reads against the truth
"""Read a CV PDF the way a machine does.

An ATS, and any LLM screening layer on top of it, never sees the rendered page.
It sees the string a text extractor recovers. Extractors disagree, so this runs
three with different strategies:

  pdfminer.six  layout-aware; rebuilds reading order from glyph positions
  pypdf         content-stream order, like the PDFBox/Tika family under many ATS
  pymupdf       the MuPDF engine, a third implementation

  read-cv-pdf.py extract CV.pdf --out DIR [--json]
      writes DIR/<extractor>.txt and DIR/extract.json, prints the checks.
      None of the checks need to know what the CV says.

  read-cv-pdf.py compare --expected EXPECTED.json DIR/reads/*.json [--json]
      diffs each blind read (one JSON per extractor, same shape as EXPECTED)
      against the expected record and against each other.

Record shape (expected and reads alike; unknown keys are ignored):
  {"name": "", "emails": [], "phones": [], "links": [], "location": "",
   "roles": [{"title": "", "employment_type": "", "company": "", "start": "", "end": "",
              "first_bullet": ""}],
   "education": [{"degree": "", "institution": "", "start": "", "end": ""}],
   "skills": []}

Exit: 0 no FAIL (warnings allowed) · 1 a FAIL · 2 could not run.
No score is produced on purpose: ATS "scores" are vendor heuristics.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

FAIL, WARN, PASS, INFO = "FAIL", "WARN", "PASS", "INFO"


@dataclass
class Result:
    check: str
    status: str
    detail: str
    why: str = ""


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, check: str, status: str, detail: str, why: str = "") -> None:
        self.results.append(Result(check, status, detail, why))

    @property
    def failed(self) -> bool:
        return any(r.status == FAIL for r in self.results)


# --------------------------------------------------------------------------
# extraction


def extract(pdf: Path) -> dict:
    import logging

    import pymupdf
    from pdfminer.high_level import extract_text
    from pypdf import PdfReader

    logging.getLogger("pdfminer").setLevel(logging.ERROR)
    pymupdf.TOOLS.mupdf_display_errors(False)

    reader = PdfReader(str(pdf))
    page_texts = {
        "pdfminer.six": [extract_text(str(pdf), page_numbers=[i]) for i in range(len(reader.pages))],
        "pypdf": [page.extract_text() or "" for page in reader.pages],
    }
    texts = {
        "pdfminer.six": extract_text(str(pdf)),
        "pypdf": "\n".join(page_texts["pypdf"]),
    }

    links: list[str] = []
    for page in reader.pages:
        for annot in page.get("/Annots") or []:
            uri = (annot.get_object().get("/A") or {}).get("/URI")
            if uri:
                links.append(str(uri))

    hidden: list[dict] = []
    with pymupdf.open(str(pdf)) as doc:
        page_texts["pymupdf"] = [page.get_text() for page in doc]
        texts["pymupdf"] = "\n".join(page_texts["pymupdf"])
        pages = doc.page_count
        meta = {k: (doc.metadata or {}).get(k) or "" for k in ("title", "author", "subject")}
        for number, page in enumerate(doc, 1):
            area = page.rect
            for span in page.get_texttrace():
                text = "".join(chr(c[0]) for c in span.get("chars", ())).strip()
                if not text:
                    continue
                reasons = []
                if span.get("type") == 3:
                    reasons.append("invisible render mode")
                if span.get("opacity", 1) == 0:
                    reasons.append("zero opacity")
                if span.get("size", 10) < 3:
                    reasons.append(f"{span.get('size'):.1f}pt")
                colour = span.get("color") or ()
                if len(colour) == 3 and min(colour) > 0.97:
                    reasons.append("white fill")
                box = pymupdf.Rect(span.get("bbox"))
                if not box.intersects(area):
                    reasons.append("off the page")
                if reasons:
                    hidden.append({"page": number, "text": text[:80], "why": reasons})

    return {"texts": texts, "page_texts": page_texts, "links": links, "pages": pages,
            "meta": meta, "hidden": hidden}


def render_pages(pdf: Path, out: Path) -> list[str]:
    """PNG of every page, what a person (and a model shown page images) sees."""
    import pymupdf

    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with pymupdf.open(str(pdf)) as doc:
        for number, page in enumerate(doc, 1):
            path = out / f"page-{number}.png"
            page.get_pixmap(dpi=110).save(str(path))
            paths.append(str(path.resolve()))
    return paths


# --------------------------------------------------------------------------
# checks that need no knowledge of the CV

MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|"
          "june|july|august|september|october|november|december")
MONTH_NUMBER = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
DATE = (rf"(?:(?:{MONTHS})\.?\s+\d{{4}}|\d{{1,2}}[/.]\d{{4}}|\d{{4}}[-/]\d{{2}}|\d{{4}})")
CURRENT = r"present|current|now|ongoing|today|date"
RANGE = re.compile(rf"\b({DATE})\s*(?:[–—-]|\bto\b)\s*({DATE}|{CURRENT})\b", re.I)
CAPS_WITH_SPACES = re.compile(r"^\s*([A-Z]{1,}(?:\s+[A-Z]+)+)\s*$", re.M)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")
PHONE = re.compile(r"\+?\d[\d ()./-]{7,}\d")
# A profile is the root of an account (github.com/<user>, linkedin.com/in/<user>),
# not a deep link to a repo, post or company page mentioned inline.
PROFILE_HOSTS = re.compile(r"(?:[\w-]+\.)?(?:linkedin\.com/in/[^/]+|(?:github\.com|gitlab\.com|"
                           r"behance\.net|dribbble\.com|x\.com|twitter\.com)/[^/]+|"
                           r"stackoverflow\.com/users/\d+(?:/[^/]+)?)$")
LIGATURES = re.compile("[ﬀ-ﬆ]")
INJECTION = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|system prompt|"
    r"you are an? (?:ai|assistant|language model|llm)|rank this (?:candidate|resume)|"
    r"(?:recommend|shortlist) this candidate", re.I)
STANDARD_HEADINGS = {
    "experience": ("experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history"),
    "education": ("education", "education and training", "academic background"),
    "skills": ("skills", "technical skills", "core skills", "core competencies", "competencies"),
    "summary": ("summary", "professional summary", "profile", "about", "about me"),
    "projects": ("projects", "selected projects"),
    "certifications": ("certifications", "certificates", "licenses"),
    "awards": ("awards", "achievements", "honors", "honours", "awards and achievements"),
    "other": ("publications", "languages", "volunteer", "volunteering", "interests",
              "extracurricular", "extracurricular activities", "activities", "references"),
}


def date_kind(token: str) -> str:
    t = token.strip().lower()
    if re.fullmatch(CURRENT, t):
        return "current"
    if re.fullmatch(r"\d{4}", t):
        return "year"
    if re.fullmatch(r"\d{1,2}[/.]\d{4}", t):
        return "MM/YYYY"
    if re.fullmatch(r"\d{4}[-/]\d{2}", t):
        return "YYYY-MM"
    return "Mon YYYY"


def icon_glyphs(text: str) -> list[str]:
    out = []
    for ch in text:
        cp = ord(ch)
        if (0xE000 <= cp <= 0xF8FF or 0x1F300 <= cp <= 0x1FAFF or 0x2700 <= cp <= 0x27BF
                or cp == 0xFFFD):
            out.append(ch)
    return out


def stranded_letters(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"\s(\S)\s", text)
            if not m.group(1).isascii() and unicodedata.category(m.group(1)).startswith("L")]


def word_set(text: str) -> set[str]:
    return set(re.findall(r"\w{3,}", text.lower()))


def heading_lines(text: str) -> set[str]:
    found = set()
    for line in text.splitlines():
        clean = re.sub(r"[^\w& ]", "", line).strip().lower()
        clean = re.sub(r"\s+", " ", clean)
        if 0 < len(clean.split()) <= 4:
            found.add(clean)
    return found


def run_checks(data: dict) -> Report:
    texts, links = data["texts"], data["links"]
    report = Report()

    short = [n for n, t in texts.items() if len(t.strip()) < 200]
    report.add("text is extractable", FAIL if short else PASS,
               f"almost no text from {', '.join(short)}" if short
               else " · ".join(f"{n}: {len(t):,} chars" for n, t in texts.items()),
               "an image-only or scanned PDF gives every parser and AI reader nothing")

    unmapped = {n: len(re.findall(r"\(cid:\d+\)", t)) for n, t in texts.items()}
    unmapped = {n: c for n, c in unmapped.items() if c}
    report.add("every glyph maps to a character", FAIL if unmapped else PASS,
               "; ".join(f"{n}: {c} unmapped (cid:N) glyphs" for n, c in unmapped.items())
               if unmapped else "no unmapped glyphs",
               "a font without a ToUnicode map turns words into (cid:N) codes")

    sets = {n: word_set(t) for n, t in texts.items()}
    names = list(sets)
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            union = sets[a] | sets[b]
            pairs.append((a, b, len(sets[a] & sets[b]) / len(union) if union else 1.0))
    worst = min(pairs, key=lambda p: p[2])
    report.add("extractors agree on the words", WARN if worst[2] < 0.9 else PASS,
               " · ".join(f"{a}/{b}: {s:.0%}" for a, b, s in pairs),
               "low overlap means one extractor splits or fuses words the others keep whole")

    offenders = {}
    caps_words = {w for t in texts.values() for w in re.findall(r"\b[A-Z]{4,}\b", t)}
    for n, t in texts.items():
        for line in CAPS_WITH_SPACES.findall(t):
            if line.replace(" ", "") in caps_words or re.fullmatch(r"(?:[A-Z] )+[A-Z]", line):
                offenders.setdefault(n, line.strip())
    report.add("headings are whole words", FAIL if offenders else PASS,
               "; ".join(f"{n} reads {v!r}" for n, v in offenders.items())
               if offenders else "no letter-spaced headings",
               "CSS letter-spacing becomes real spaces, so the parser cannot find the section")

    stranded = {n: stranded_letters(t) for n, t in texts.items()}
    stranded = {n: v for n, v in stranded.items() if v}
    report.add("accented letters stay inside their word", WARN if stranded else PASS,
               "; ".join(f"{n}: {len(v)} stranded ({''.join(sorted(set(v)))})"
                         for n, v in stranded.items()) if stranded else "none stranded",
               "a font split by unicode-range emits accented letters as separate runs; names break")

    ligs = {n: sorted(set(LIGATURES.findall(t))) for n, t in texts.items()}
    ligs = {n: v for n, v in ligs.items() if v}
    report.add("no ligature glyphs", WARN if ligs else PASS,
               "; ".join(f"{n}: {''.join(v)}" for n, v in ligs.items()) if ligs else "none",
               "'ﬁ' is one character, so a keyword search for 'notification' misses 'notiﬁcation'")

    icons = {n: icon_glyphs(t) for n, t in texts.items()}
    icons = {n: v for n, v in icons.items() if v}
    report.add("no icon or replacement glyphs", WARN if icons else PASS,
               "; ".join(f"{n}: {len(v)} ({''.join(sorted(set(v)))[:12]})" for n, v in icons.items())
               if icons else "none",
               "icon fonts and emoji extract as junk; contact icons lose their meaning")

    ranges = {n: RANGE.findall(t) for n, t in texts.items()}
    counts = " · ".join(f"{n}: {len(r)}" for n, r in ranges.items())
    best = max(ranges.values(), key=len)
    if not best:
        report.add("date ranges parse", FAIL, "no date range found by any extractor",
                   "employment dates drive the years-of-experience calculation")
    else:
        lengths = {len(r) for r in ranges.values()}
        report.add("date ranges parse", WARN if len(lengths) > 1 else PASS,
                   f"ranges found: {counts}",
                   "extractors finding different counts means a range breaks in some of them")
        kinds = [date_kind(x) for r in best for x in r if date_kind(x) != "current"]
        year_only = [f"{a} – {b}" for a, b in best if date_kind(a) == "year"]
        mixed = sorted(set(kinds))
        detail = []
        if year_only:
            detail.append(f"{len(year_only)} year-only ({', '.join(year_only[:5])})")
        if len(mixed) > 1:
            detail.append(f"formats mixed: {', '.join(mixed)}")
        report.add("dates carry a month, in one format", WARN if detail else PASS,
                   "; ".join(detail) or f"all {mixed[0] if mixed else '?'}",
                   "year-only ranges are the most common field that comes back blank")
        currents = sorted({b.lower() for _, b in best if date_kind(b) == "current"})
        odd = [c for c in currents if c != "present"]
        if currents:
            report.add("current role ends in 'Present'", WARN if odd else PASS,
                       f"uses {', '.join(odd)}" if odd else "Present",
                       "some parsers (iCIMS) recognise only 'Present'")

    for n, t in texts.items():
        top = "\n".join([ln for ln in t.splitlines() if ln.strip()][:15])
        if not EMAIL.search(t):
            report.add(f"email present ({n})", FAIL, "no email address in the text",
                       "the email is the primary contact field everywhere")
        elif not EMAIL.search(top):
            report.add(f"contact near the top ({n})", WARN,
                       "no email in the first 15 lines",
                       "Workday looks for contact details in the first lines; headers may be dropped")
    if all(EMAIL.search(t) for t in texts.values()):
        phone_top = all(PHONE.search("\n".join([ln for ln in t.splitlines() if ln.strip()][:15]))
                        for t in texts.values())
        report.add("email (and phone) at the top", PASS if phone_top else INFO,
                   "found in the first 15 lines" + ("" if phone_top else "; no phone there"))

    alltext = "\n".join(texts.values())
    bare_text = re.sub(r"\s", "", alltext.lower())
    # Inline links whose visible text is a company or project name are normal.
    # Profile links are contact fields, so they have to survive as text.
    profiles, inline_only = [], 0
    for uri in dict.fromkeys(links):
        if uri.startswith(("mailto:", "tel:")):
            continue
        bare = re.sub(r"^https?://(www\.)?", "", uri).rstrip("/").lower()
        if not bare or bare in bare_text:
            continue
        if PROFILE_HOSTS.match(bare):
            profiles.append(bare)
        else:
            inline_only += 1
    report.add("profile links readable as text", WARN if profiles else PASS,
               f"only as annotations: {', '.join(profiles)}" if profiles
               else "every profile link appears in the text"
               + (f" ({inline_only} other links are annotations only, which is fine)" if inline_only else ""),
               "a parser that ignores annotations gets no profile URL; show the bare domain path")

    found = {n: heading_lines(t) for n, t in texts.items()}
    present = {sec for sec, names_ in STANDARD_HEADINGS.items()
               if any(any(h == x for x in names_) for hs in found.values() for h in hs)}
    core_missing = [s for s in ("experience", "education", "skills") if s not in present]
    report.add("standard section headings", WARN if core_missing else PASS,
               f"found: {', '.join(sorted(present)) or 'none'}"
               + (f"; not found: {', '.join(core_missing)}" if core_missing else ""),
               "a creative heading ('What I've Built') is a section the parser cannot scope")

    if data["hidden"]:
        sample = data["hidden"][0]
        report.add("no hidden text", WARN,
                   f"{len(data['hidden'])} spans hidden ({', '.join(sample['why'])}: "
                   f"{sample['text']!r}, p{sample['page']})",
                   "AI screeners flag invisible or white text as manipulation; white text on a "
                   "dark band is a false positive, check the page")
    else:
        report.add("no hidden text", PASS, "no invisible, white, tiny or off-page text")

    injected = sorted({m.group(0) for m in INJECTION.finditer(alltext)})
    report.add("no instructions aimed at an AI", FAIL if injected else PASS,
               f"found: {', '.join(injected)}" if injected else "none",
               "prompt injection in a CV is detected and gets the application flagged")

    meta = data["meta"]
    empty = [k for k in ("title", "author") if not meta.get(k)]
    report.add("PDF metadata set", INFO if empty else PASS,
               f"empty: {', '.join(empty)}" if empty
               else f"title {meta['title']!r}, author {meta['author']!r}",
               "browser exports leave Author empty; some parsers read the name from it")

    layout, naive = texts["pdfminer.six"], texts["pypdf"]
    layout_tokens = set(re.findall(r"[a-z]{4,}", layout.lower()))
    fused = sorted({t for t in re.findall(r"[a-z]{13,}", naive.lower()) if t not in layout_tokens})
    if fused:
        report.add("words not fused across line breaks", WARN,
                   f"{len(fused)} fused in pypdf: {', '.join(fused[:4])}" + (" …" if len(fused) > 4 else ""),
                   "keyword matching misses the fused terms")

    report.add("pages", INFO, f"{data['pages']}")
    return report


# --------------------------------------------------------------------------
# compare blind reads with the expected record


def norm(s) -> str:
    # Fold case and accents both: small caps extract as capitals, and Turkish
    # NIŞANTAŞI lowercases to "nişantaşi" while the record says "Nişantaşı".
    s = unicodedata.normalize("NFKD", str(s or "").replace("ı", "i")).casefold()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^\w@+.# ]", " ", s)).strip()


def norm_date(s) -> str:
    t = str(s or "").strip().lower()
    if not t:
        return ""
    if re.fullmatch(CURRENT, t):
        return "present"
    m = re.fullmatch(rf"({MONTHS})\.?\s+(\d{{4}})", t)
    if m:
        return f"{m.group(2)}-{MONTH_NUMBER[m.group(1)[:3]]:02d}"
    m = re.fullmatch(r"(\d{1,2})[/.](\d{4})", t)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{4})[-/](\d{2})", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return t


def same(a, b) -> bool:
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def compare(expected: dict, reads: dict[str, dict]) -> dict:
    rows: list[dict] = []

    def row(reader: str, fld: str, want, got, status: str) -> None:
        rows.append({"reader": reader, "field": fld, "expected": want, "got": got, "status": status})

    for reader, got in reads.items():
        if expected.get("name"):
            ok = norm(got.get("name")) == norm(expected["name"])
            row(reader, "name", expected["name"], got.get("name"), PASS if ok else FAIL)

        for key, digits in (("emails", False), ("phones", True)):
            want = expected.get(key) or []
            if not want:
                continue
            fix = (lambda x: re.sub(r"\D", "", str(x))[-9:]) if digits else norm
            have = {fix(x) for x in got.get(key) or []}
            lost = [w for w in want if fix(w) not in have]
            row(reader, key, want, got.get(key), FAIL if lost else PASS)

        want_links = {re.sub(r"^https?://(www\.)?", "", norm(x)).rstrip("/") for x in expected.get("links") or []}
        if want_links:
            have = {re.sub(r"^https?://(www\.)?", "", norm(x)).rstrip("/") for x in got.get("links") or []}
            lost = sorted(w for w in want_links if not any(w in h or h in w for h in have))
            row(reader, "links", f"{len(want_links)}", f"missing: {', '.join(lost)}" if lost else "all",
                WARN if lost else PASS)

        got_roles = list(got.get("roles") or [])
        for i, role in enumerate(expected.get("roles") or []):
            label = f"role {i + 1}: {role.get('company')}"
            match = next((r for r in got_roles if same(r.get("company"), role.get("company"))), None)
            if match is None:
                by_title = next((r for r in got_roles if same(r.get("title"), role.get("title"))
                                 and norm_date(r.get("start")) == norm_date(role.get("start"))), None)
                row(reader, f"{label} company", role.get("company"),
                    by_title.get("company") if by_title else None, FAIL)
                if by_title is None:
                    continue
                match = by_title
            got_roles.remove(match)
            wrong = False
            if role.get("title"):
                if not same(match.get("title"), role.get("title")):
                    row(reader, f"{label} title", role.get("title"), match.get("title"), FAIL)
                    wrong = True
                elif norm(match.get("title")) != norm(role.get("title")):
                    # Contained but not equal: the rest is a qualifier such as
                    # "Intern" or "Part-Time". Lost from both fields, it changes
                    # what the role means (an internship read as a full job).
                    kept = norm(f"{match.get('title')} {match.get('employment_type') or ''}")
                    rest = norm(role["title"]).replace(norm(match.get("title")), "").split()
                    if not all(w in kept for w in rest):
                        row(reader, f"{label} title", role.get("title"), match.get("title"), WARN)
                        wrong = True
            for d in ("start", "end"):
                if role.get(d) and norm_date(match.get(d)) != norm_date(role.get(d)):
                    row(reader, f"{label} {d}", role.get(d), match.get(d), FAIL)
                    wrong = True
            if not wrong:
                row(reader, label, role.get("title"), match.get("title"), PASS)
            if role.get("first_bullet"):
                words = norm(role["first_bullet"]).split()[:4]
                gotb = norm(match.get("first_bullet"))
                if " ".join(words) not in gotb:
                    row(reader, f"{label} first bullet", " ".join(words), match.get("first_bullet"), WARN)
        for extra in got_roles:
            row(reader, "extra role", None, f"{extra.get('title')} at {extra.get('company')}", WARN)

        # Degree and institution as a pair: two degrees from different schools
        # swapped between them would pass a check on institutions alone.
        for i, edu in enumerate(expected.get("education") or []):
            label = f"education {i + 1}: {edu.get('degree') or edu.get('institution')}"
            entries = got.get("education") or []
            match = next((e for e in entries if same(e.get("degree"), edu.get("degree"))), None) \
                if edu.get("degree") else None
            if match is None:
                match = next((e for e in entries if same(e.get("institution"), edu.get("institution"))), None)
            ok = match is not None and same(match.get("institution"), edu.get("institution"))
            row(reader, label, f"{edu.get('degree')} at {edu.get('institution')}",
                f"{match.get('degree')} at {match.get('institution')}" if match else None,
                PASS if ok else FAIL)

        want_skills = [norm(s) for s in expected.get("skills") or []]
        if want_skills:
            have = " | ".join(norm(s) for s in got.get("skills") or [])
            lost = [s for s in want_skills if s not in have]
            row(reader, "skills", f"{len(want_skills)}",
                f"{len(want_skills) - len(lost)} recovered" + (f"; missed {', '.join(lost[:5])}" if lost else ""),
                WARN if len(lost) > len(want_skills) * 0.2 else PASS)

    by_field: dict[str, set] = {}
    for r in rows:
        by_field.setdefault(r["field"], set()).add((r["reader"], r["status"]))
    split = sorted(f for f, s in by_field.items()
                   if len({st for _, st in s}) > 1 and len({rd for rd, _ in s}) > 1)
    return {"rows": rows, "extractor_dependent": split,
            "failed": any(r["status"] == FAIL for r in rows)}


# --------------------------------------------------------------------------
# the page: what different agents see

READER_ORDER = ("native", "pypdf", "pdfminer.six", "pymupdf")
READER_INPUT = {
    "native": "the PDF itself, opened with the reader's own file tool. A model API given a PDF "
              "receives its text layer and an image of each page: the images are the page "
              "sections below; the text layer it was given is not known.",
    "pypdf": "the plain text pypdf recovered, shown in the page sections. pypdf is the default "
             "PDF reader behind LlamaIndex's SimpleDirectoryReader, the likeliest string for a "
             "company that feeds uploads to an agent through a framework.",
    "pdfminer.six": "the plain text pdfminer.six recovered: layout-aware, it rebuilds reading "
                    "order from glyph positions.",
    "pymupdf": "the plain text pymupdf (the MuPDF engine) recovered.",
}
STRAY = re.compile(r"^\s*(?:[A-Za-z]{1,3}\s*){1,3}$")


def mark_line(line: str) -> str:
    """Escape a line of extracted text and mark what the checks would flag in it."""
    import html

    if line.strip() and (STRAY.match(line) or CAPS_WITH_SPACES.fullmatch(line)):
        why = "letter-spaced heading" if CAPS_WITH_SPACES.fullmatch(line) else "stray fragment"
        return f'<mark title="{why}">{html.escape(line)}</mark>'
    out = []
    for ch in line:
        if LIGATURES.match(ch) or icon_glyphs(ch):
            out.append(f'<mark title="glyph">{html.escape(ch)}</mark>')
        else:
            out.append(html.escape(ch))
    text = "".join(out)
    return re.sub(r"\(cid:\d+\)", lambda m: f'<mark title="unmapped glyph">{m.group(0)}</mark>', text)


def heading_order(text: str) -> list[str]:
    names = {n for group in STANDARD_HEADINGS.values() for n in group}
    order = []
    for line in text.splitlines():
        clean = re.sub(r"\s+", " ", re.sub(r"[^\w& ]", "", line)).strip()
        if clean.lower() in names:
            order.append(clean)
    return order


def page_sections(run: Path) -> tuple[str, list[tuple[str, str]]]:
    import base64
    import html

    esc = html.escape
    ext = json.loads((run / "extract.json").read_text(encoding="utf-8"))
    cmp_path = run / "compare.json"
    cmp = json.loads(cmp_path.read_text(encoding="utf-8")) if cmp_path.exists() else {"rows": [], "reads": {}}
    reads = {}
    for name, path in cmp.get("reads", {}).items():
        try:
            reads[name] = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            reads[name] = None
    order = [r for r in READER_ORDER if r in reads] + sorted(r for r in reads if r not in READER_ORDER)
    rows = cmp.get("rows", [])
    title = Path(ext["pdf"]).name
    sections: list[tuple[str, str]] = []

    tiles = []
    for name in order:
        mine = [r for r in rows if r["reader"] == name]
        right = sum(r["status"] == PASS for r in mine)
        tiles.append(f'<div class="ws-stat"><span class="ws-stat__value">{right}/{len(mine)}</span>'
                     f'<span class="ws-stat__label">{esc(name)}: fields right</span></div>')
    results = ext.get("results", [])
    fails = sum(r["status"] == FAIL for r in results)
    warns = sum(r["status"] == WARN for r in results)
    tiles.append(f'<div class="ws-stat"><span class="ws-stat__value">{fails} / {warns}</span>'
                 f'<span class="ws-stat__label">text checks failed / warned</span></div>')
    sections.append(("Summary", (
        f"<p>What four blind AI readers understood from <code>{esc(title)}</code>, "
        f"{ext.get('pages')} pages, against the CV's own record.</p>"
        f'<div class="ws-stats ws-stats--tiles">{"".join(tiles)}</div>'
        '<div class="ws-callout"><p>These are stand-ins. Commercial ATS parsers (Workday, '
        "Greenhouse and the like) are closed and cannot be run here. Each view is what an agent "
        "fed by that reader sees, not what a named vendor sees.</p></div>")))

    issues = [r for r in results if r["status"] in (FAIL, WARN)]
    body = "<p>No text check failed or warned.</p>"
    if issues:
        body = ("<table class=\"ws-table--wrap\"><thead><tr><th>Check</th><th>Status</th><th>Found, and why it matters</th>"
                "</tr></thead><tbody>" + "".join(
                    f"<tr><td>{esc(r['check'])}</td><td>{r['status']}</td><td>{esc(r['detail'])}"
                    f"<br><small>{esc(r['why'])}</small></td></tr>" for r in issues) + "</tbody></table>")
    sections.append(("Issues found", body))

    cards = []
    for name in order:
        wrong = [r for r in rows if r["reader"] == name and r["status"] != PASS]
        if reads.get(name) is None:
            inner = "<p>No valid read was recorded.</p>"
        elif not wrong:
            inner = "<p>Every scored field right.</p>"
        else:
            inner = ("<table class=\"ws-table--wrap\"><thead><tr><th>Field</th><th>Expected</th><th>Got</th></tr></thead><tbody>"
                     + "".join(f"<tr><td>{esc(r['field'])}</td><td>{esc(str(r['expected']))}</td>"
                               f"<td>{esc(str(r['got']))}</td></tr>" for r in wrong) + "</tbody></table>")
        cards.append(f'<div class="ws-card"><h3>{esc(name)}</h3>'
                     f'<p class="ws-card__desc">Input: {esc(READER_INPUT.get(name, "unknown"))}</p>{inner}</div>')
    sections.append(("What each reader got wrong", "".join(cards) or "<p>No reads were compared.</p>"))

    quotes = []
    for name in order:
        rec = reads.get(name) or {}
        failed = any(r["reader"] == name and r["status"] == FAIL for r in rows)
        quotes.append(f"<h3>{esc(name)}{' (has wrong fields)' if failed else ''}: "
                      f"{rec.get('years_of_experience', '?')} years of experience</h3>"
                      f"<blockquote><p>{esc(rec.get('recruiter_summary') or '')}</p></blockquote>")
    sections.append(("Recruiter summaries", (
        "<p>What each reader would show a recruiter instead of the CV. A summary can misstate "
        "facts its reader parsed correctly, so read each against the CV: the scores above do "
        "not cover them.</p>" + "".join(quotes))))

    images = ext.get("page_images", [])
    texts = ext.get("page_texts", {})
    for i in range(ext.get("pages", 0)):
        img = ""
        if i < len(images) and Path(images[i]).exists():
            data = base64.b64encode(Path(images[i]).read_bytes()).decode()
            img = f'<img src="data:image/png;base64,{data}" alt="Page {i + 1} as rendered">'

        def pre(name: str) -> str:
            lines = (texts.get(name) or [""] * (i + 1))[i].splitlines()
            # Capped near the page image's height so the two sit side by side.
            return ('<pre style="max-height:48rem;overflow:auto"><code>'
                    + "\n".join(mark_line(ln) for ln in lines) + "</code></pre>")

        heads = "".join(f"<li><strong>{esc(n)}</strong>: {esc(' → '.join(heading_order(texts[n][i])) or 'none')}</li>"
                        for n in ("pypdf", "pdfminer.six", "pymupdf") if n in texts)
        body = (
            '<div class="ws-compare">'
            f'<div class="ws-compare__side"><p class="ws-compare__label">Rendered page</p>{img}</div>'
            f'<div class="ws-compare__side" data-side="proposed"><p class="ws-compare__label">pypdf text</p>{pre("pypdf")}</div>'
            "</div>"
            f"<p>Section headings in the order each extractor emits them:</p><ul>{heads}</ul>"
            + "".join(f"<details><summary>{esc(n)} text</summary>{pre(n)}</details>"
                      for n in ("pdfminer.six", "pymupdf") if n in texts))
        sections.append((f"Page {i + 1}", body))

    problems = []
    for name in order:
        items = (reads.get(name) or {}).get("problems") or []
        seen = (reads.get(name) or {}).get("instructions_seen") or []
        lis = "".join(f"<li>{esc(p)}</li>" for p in items)
        extra = f"<p>Text addressed to an AI: {esc('; '.join(seen))}</p>" if seen else ""
        problems.append(f"<details><summary>{esc(name)}: {len(items)}</summary><ul>{lis}</ul>{extra}</details>")
    sections.append(("Problems the readers raised", "".join(problems)))
    return title, sections


def fallback_page(title: str, headings: list[str]) -> str:
    """A plain page when project-lifecycle is not installed."""
    import html

    slug = lambda h: re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")
    toc = "".join(f'<li><a href="#{slug(h)}">{html.escape(h)}</a></li>' for h in headings)
    secs = "".join(f'<section id="{slug(h)}">\n<h2>{html.escape(h)}</h2>\n<p></p>\n</section>\n' for h in headings)
    return ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width,initial-scale=1\"><title>" + html.escape(title) + "</title><style>"
            ":root{color-scheme:light dark}body{font:16px/1.5 system-ui,sans-serif;max-width:72rem;margin:2rem auto;padding:0 1rem}"
            "pre{white-space:pre-wrap;font-size:.8rem}img{max-width:100%;border:1px solid #8884}"
            "mark{background:#fd04;color:inherit}table{border-collapse:collapse}td,th{border:1px solid #8884;padding:.3rem;vertical-align:top}"
            ".ws-compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}"
            "@media(max-width:44rem){.ws-compare{grid-template-columns:1fr}}.ws-stats{display:flex;gap:1rem;flex-wrap:wrap}"
            ".ws-stat{display:flex;flex-direction:column;border:1px solid #8884;padding:.5rem}.ws-stat__value{font-size:1.5rem}"
            ".ws-card,.ws-callout{border:1px solid #8884;padding:.5rem 1rem;margin:1rem 0}"
            "</style></head><body><h1>" + html.escape(title) + "</h1><nav><ul>" + toc + "</ul></nav><main>"
            + secs + "</main></body></html>")


def git_unignored(path: Path) -> str | None:
    """The repo root when `path` sits inside a git repo and git does not ignore it."""
    import subprocess

    parent = path.resolve().parent
    parent.mkdir(parents=True, exist_ok=True)
    top = subprocess.run(["git", "-C", str(parent), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode != 0:
        return None
    ignored = subprocess.run(["git", "-C", str(parent), "check-ignore", "-q", str(path.resolve())])
    return None if ignored.returncode == 0 else top.stdout.strip()


def cmd_page(args) -> int:
    import shutil
    import subprocess

    run, out = Path(args.run), Path(args.out)
    if not (run / "extract.json").exists():
        print(f"read-cv-pdf: {run}/extract.json missing; run extract first", file=sys.stderr)
        return 2
    if not (run / "compare.json").exists():
        print(f"read-cv-pdf: {run}/compare.json missing; run compare first (the page shows its result)",
              file=sys.stderr)
        return 2
    repo = git_unignored(out)
    if repo:
        print(f"read-cv-pdf: {out} is inside the git repo {repo} and not ignored. The page carries the "
              "CV's contact details: write it to a folder that repo ignores, or ask before adding one "
              "to its .gitignore.", file=sys.stderr)
        return 2
    title, sections = page_sections(run)
    heading = f"How agents read {title}"
    headings = [h for h, _ in sections]
    if shutil.which("project-lifecycle"):
        cmd = ["project-lifecycle", "page-new", "--title", "Agent views of a CV", "--inline",
               "--description", heading, "--out", str(out)]
        for h in headings:
            cmd += ["--section", h]
        if args.session:
            cmd += ["--session", args.session]
        if out.exists():
            out.unlink()
        made = subprocess.run(cmd, capture_output=True, text=True)
        if made.returncode != 0:
            print(f"read-cv-pdf: page-new failed: {made.stderr.strip()}", file=sys.stderr)
            return 2
        page = out.read_text(encoding="utf-8")
    else:
        page = fallback_page(heading, headings)
    for h, body in sections:
        page, n = re.subn(rf"(<h2>{re.escape(h)}</h2>\s*)<p></p>", lambda m: m.group(1) + body, page, count=1)
        if not n:
            print(f"read-cv-pdf: no empty section {h!r} to fill in the page skeleton", file=sys.stderr)
            return 2
    out.write_text(page, encoding="utf-8")
    print(out.resolve())
    return 0


# --------------------------------------------------------------------------
# output


def print_report(results: list[Result]) -> None:
    width = max(len(r.check) for r in results)
    for r in results:
        print(f"  {r.status:<4}  {r.check:<{width}}  {r.detail}")
        if r.why and r.status in (FAIL, WARN):
            print(f"        {'':<{width}}  └ {r.why}")


def cmd_extract(args) -> int:
    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"read-cv-pdf: no such file {pdf}", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data = extract(pdf)
    for name, text in data["texts"].items():
        (out / f"{name}.txt").write_text(text, encoding="utf-8")
    report = run_checks(data)
    summary = {"pdf": str(pdf.resolve()), "pages": data["pages"], "meta": data["meta"],
               "links": data["links"], "hidden": data["hidden"][:20],
               "texts": {n: str((out / f"{n}.txt").resolve()) for n in data["texts"]},
               "page_texts": data["page_texts"],
               "page_images": render_pages(pdf, out / "pages"),
               "results": [asdict(r) for r in report.results], "failed": report.failed}
    (out / "extract.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"{pdf.name}: {data['pages']} pages, {len(data['links'])} link annotations")
        print_report(report.results)
        print(f"\ntext per extractor: {out.resolve()}/<extractor>.txt")
    return 1 if report.failed else 0


def cmd_compare(args) -> int:
    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    reads = {}
    for p in args.reads:
        path = Path(p)
        try:
            reads[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"read-cv-pdf: {path} is not JSON ({exc})", file=sys.stderr)
            return 2
    result = compare(expected, reads)
    result["reads"] = {name: str(Path(p).resolve()) for name, p in zip(reads, args.reads)}
    saved = Path(args.expected).resolve().parent / "compare.json"
    saved.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["failed"] else 0
    bad = [r for r in result["rows"] if r["status"] != PASS]
    total = {rd: sum(1 for r in result["rows"] if r["reader"] == rd) for rd in reads}
    for rd in reads:
        wrong = sum(1 for r in bad if r["reader"] == rd)
        print(f"  {rd}: {total[rd] - wrong}/{total[rd]} fields right")
    for r in bad:
        print(f"  {r['status']:<4}  {r['reader']:<14} {r['field']}: expected {r['expected']!r}, got {r['got']!r}")
    if result["extractor_dependent"]:
        print(f"\nright in one reader, wrong in another: {', '.join(result['extractor_dependent'])}")
        print("  the difference is the extractor's text, not the reader: look at those .txt files")
    return 1 if result["failed"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="extract text with three engines and check it")
    p.add_argument("pdf")
    p.add_argument("--out", required=True, help="folder for <extractor>.txt and extract.json")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_extract)
    c = sub.add_parser("compare", help="diff blind reads against the expected record")
    c.add_argument("--expected", required=True)
    c.add_argument("reads", nargs="+", help="one JSON per extractor, named <extractor>.json")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_compare)
    g = sub.add_parser("page", help="write the HTML page of what each agent saw")
    g.add_argument("--run", required=True, help="the folder extract and compare wrote to")
    g.add_argument("--out", required=True, help="the .html to write; refused inside a repo unless git ignores it")
    g.add_argument("--session", help="session id, for the page's provenance stamp")
    g.set_defaults(func=cmd_page)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
