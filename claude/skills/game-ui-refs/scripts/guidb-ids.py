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
"""

import argparse
import gzip
import html
import re
import sys
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


def main():
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
        "— `set=1` lists screens (`set=0` lists games), `vid=1` restricts to videos,",
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
