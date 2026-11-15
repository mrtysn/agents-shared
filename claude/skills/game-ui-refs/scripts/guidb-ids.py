#!/usr/bin/env python3
# DESC: Regenerate Game UI Database's screen-category and tag-filter ID tables from its latest Wayback snapshot
"""
guidb-ids: Build the ID tables /game-ui-refs uses to compose filtered
gameuidatabase.com links (scrn=, tag=, plat=).

Reads the homepage from the Wayback Machine, never from the live site — the site
answers automated clients with a Cloudflare challenge, and an archived copy costs
it nothing. Writes Markdown to stdout; redirect it over references/guidb-ids.md.

    guidb-ids.py > references/guidb-ids.md
    guidb-ids.py --html saved_homepage.html > references/guidb-ids.md
    guidb-ids.py lookup level select        the matching IDs, with their neighbours in the same group

`lookup` reads the generated table beside this script, so a run needs a few lines of it, never the
whole 18 KB. It matches on word stems and near-spellings, and prints the whole group of a match, so
"stage select" lands on "Mode & Screen Select" with its sibling categories to choose from.
"""

import argparse
import difflib
import gzip
import html
import re
import sys
from pathlib import Path
import urllib.request

SITE = "https://www.gameuidatabase.com/"
# A far-future timestamp redirects to the newest capture; id_ serves it as captured,
# without Wayback's link rewriting. (The availability API rate-limits far sooner.)
LATEST = f"https://web.archive.org/web/99991231235959id_/{SITE}"
UA = {"User-Agent": "Mozilla/5.0 (guidb-ids; reads the Wayback Machine)"}


def latest_snapshot():
    req = urllib.request.Request(LATEST, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        m = re.search(r"/web/(\d{14})id_/", r.geturl())
        body = r.read()
        # id_ replays the capture's own encoding, gzip included.
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return (m[1] if m else "unknown"), body.decode("utf-8", errors="replace")


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def heading_case(s):
    """The site shouts sub-headings (GOAL & NAVIGATION); keep acronyms, lower the joiners."""
    words = []
    for i, w in enumerate(s.split()):
        if w in {"HUD", "UI", "IAP", "DLC"}:
            words.append(w)
        elif i and w.lower() in {"and", "or", "of", "the"}:
            words.append(w.lower())
        else:
            words.append(w.capitalize())
    return " ".join(words)


def screen_categories(page):
    """Accordion menus: card header -> SMALL HEADING -> link, or dropdown -> sub-links."""
    rows = []
    token = re.compile(
        r'class="card-header[^"]*"[^>]*>(?P<card>.*?)</div>'
        r'|<span class="headingSmall[^"]*">(?P<heading>.*?)</span>'
        r'|<a class="animsition-link dropdown"\s*>(?P<dropdown>.*?)</a>'
        r'|(?P<subclose></div>)'
        r'|href="index\.php\?&(?:amp;)?(?:set=\d+&(?:amp;)?)?scrn=(?P<id>\d+)"[^>]*>(?P<name>.*?)</a>',
        re.S,
    )
    card = heading = parent = None
    for m in token.finditer(page):
        if m["card"] is not None:
            card, heading, parent = text(m["card"]), None, None
        elif m["heading"] is not None:
            heading, parent = heading_case(text(m["heading"])), None
        elif m["dropdown"] is not None:
            parent = text(m["dropdown"])
        elif m["subclose"] is not None:
            parent = None
        elif card:
            group = " › ".join(p for p in (card, heading, parent) if p)
            rows.append((group, text(m["name"]), int(m["id"])))
    seen, unique = set(), []
    for row in rows:
        if row[2] not in seen:
            seen.add(row[2])
            unique.append(row)
    return unique


def tag_groups(page):
    names = {
        gid: text(name)
        for gid, name in re.findall(r'data-groupid="(\d+)">([^<]+)</span>', page, re.I)
    }
    groups = []
    # The capture spells it data-groupID; a browser-saved copy lowercases it.
    blocks = re.split(r'<div[^>]*class="mobmodal_content mob_filters"[^>]*data-groupid="', page, flags=re.I)
    for block in blocks[1:]:
        gid = block.split('"', 1)[0]
        # Badges vary: `?&tag=` or `?set=1&tag=`, onclick before or after style.
        # `&` arrives raw from the capture, or as `&amp;` from a browser-saved copy.
        badge = r"index\.php\?(?:&(?:amp;)?)?(?:set=\d+&(?:amp;)?)?{}=(\d+)'[^>]*>\s*<span[^>]*>([^<]+)</span>"
        tags = re.findall(badge.format("tag"), block)
        plats = re.findall(badge.format("plat"), block)
        if tags:
            groups.append((names.get(gid, f"group {gid}"), "tag", tags))
        elif plats:
            groups.append((names.get(gid, f"group {gid}"), "plat", plats))
    return groups


TABLE = Path(__file__).resolve().parent.parent / "references" / "guidb-ids.md"


def table_rows():
    """(section, group, label, param, id) for every row of the generated Markdown."""
    rows, section, param, screens = [], "", "", False
    for line in TABLE.read_text().splitlines():
        head = re.match(r"## (.+?) \(`(\w+)=`\)", line)
        if head:
            section, param = head[1], head[2]
            screens = param == "scrn"
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not line.startswith("|") or not cells[-1].isdigit():
            continue
        if screens and len(cells) == 3:
            rows.append((section, cells[0], cells[1], param, cells[2]))
        elif len(cells) == 2:
            rows.append((section, section, cells[0], param, cells[1]))
    return rows


def stem(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def lookup(words):
    rows = table_rows()
    if not rows:
        sys.exit(f"guidb-ids: no rows read from {TABLE}; regenerate it with this script")
    wanted = [stem(w) for w in re.findall(r"[a-z0-9]+", " ".join(words).lower())]
    if not wanted:
        sys.exit("guidb-ids: give some words to look up")

    def matches(word, row):
        tokens = [stem(t) for t in re.findall(r"[a-z0-9]+", row[2].lower())]
        return any(t.startswith(word) or word.startswith(t) and len(t) > 3
                   or len(word) > 3 and difflib.SequenceMatcher(None, word, t).ratio() >= 0.86 for t in tokens)

    # A word that few rows carry says more than "menu", which dozens do: weight each by its rarity.
    weight = {w: 1 / max(1, sum(matches(w, r) for r in rows)) for w in wanted}
    scored = sorted(((sum(weight[w] for w in wanted if matches(w, r)), r) for r in rows),
                    key=lambda x: -x[0])
    chosen = [r for s, r in scored if s > 0][:8]
    if not chosen:
        print("no category matches; use the site's text search (text=<words>) and say so in coverage")
        return
    print("best matches first:")
    for section, group, label, param, ident in chosen:
        print(f"  {label} = {ident}   ({param}=, {group})")
    first = chosen[0]
    print(f"\nthe rest of the first match's group, {first[1]} ({first[3]}=):")
    for r in rows:
        if r[:2] == first[:2] and r != first:
            print(f"    {r[2]} = {r[4]}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "lookup":
        return lookup(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--html", help="parse a saved homepage instead of fetching the latest Wayback snapshot")
    args = ap.parse_args()

    if args.html:
        with open(args.html, encoding="utf-8", errors="replace") as f:
            source, page = args.html, f.read()
    else:
        ts, page = latest_snapshot()
        source = f"Wayback snapshot {ts}"

    screens = screen_categories(page)
    groups = tag_groups(page)
    if not screens:
        sys.exit("guidb-ids: found no screen categories — the page markup has changed; update the parser")

    out = [
        "# Game UI Database filter IDs",
        "",
        f"Generated by `scripts/guidb-ids.py` from {source}. Regenerate rather than edit.",
        "",
        "Compose: `https://www.gameuidatabase.com/index.php?set=1&scrn=<id>&plat=<id>&tag=<id,id>`",
        "— `set=1` lists screens (`set=0` lists games); videos are the Screen Transitions and Looping Animations tags;",
        "`hex=<rrggbb>` searches by colour, `text=<words>` searches text in images.",
        "",
        "## Screen categories (`scrn=`)",
        "",
        "| Group | Screen | scrn |",
        "|---|---|---|",
    ]
    out += [f"| {g} | {n} | {i} |" for g, n, i in screens]
    for name, param, items in groups:
        out += ["", f"## {name} (`{param}=`)", "", f"| {name} | {param} |", "|---|---|"]
        out += [f"| {text(label)} | {i} |" for i, label in items]
    print("\n".join(out))


if __name__ == "__main__":
    main()
